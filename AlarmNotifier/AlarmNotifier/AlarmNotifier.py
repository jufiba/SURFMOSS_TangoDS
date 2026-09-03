# -*- coding: utf-8 -*-
#
# This file is part of the AlarmNotifier project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" AlarmNotifier

Watches the State of other device servers and sends e-mail when one of them
says something is wrong. A deliberately small replacement for PANIC/PyAlarm.

It does not evaluate numeric thresholds. That judgement belongs next to the
data, in an AnalogInterlock running on the instrument's own Pi, where it keeps
working if this server or the network is down. Here only verdicts already
reached elsewhere are read, so a rule is a device name and a set of states.

  it does not act. Anything that must interrupt an experiment belongs in an
  interlock, and anything that must not happen at all belongs in a hardware
  chain. This server only tells you.

Failure modes and what this server does about each:

  device reports an alarm state -> e-mail after `persist` consecutive sweeps
  device unreadable             -> e-mail after UnknownCycles sweeps, which is
                                   long enough that a Starter restart or a Pi
                                   reboot passes unremarked
  device in neither set         -> held, neither trips nor recovers (INIT,
                                   MOVING, an Init from Jive)
  when= gate shut               -> GATED, not evaluated, no mail either way.
                                   For water that is deliberately closed while
                                   a magnet or an evaporator is off
  when= gate unreadable         -> evaluated anyway, because failing towards
                                   silence is the one failure worth avoiding
  mail cannot be sent           -> FAULT, LastMailError, the queue keeps the
                                   message and the next sweep retries
  this server dies              -> nothing here can catch it. The periodic
                                   report is what closes that loop: if a Monday
                                   passes with no mail at all, that is the
                                   alarm.
"""

# PyTango imports
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import device_property
from tango import AttrQuality, DispLevel, DevState
from tango import AttrWriteType
# Additional import
# PROTECTED REGION ID(AlarmNotifier.additionnal_import) ENABLED START #
import os
import sys
import json
import time
import shlex
import threading
import subprocess

try:
    import queue
except ImportError:                                   # pragma: no cover
    import Queue as queue

_DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

# Every key a rule may carry. Anything else is a typo, and a typo in an alarm
# rule that is silently ignored is how an alarm gets lost.
_KEYS = set(("name", "dev", "attr", "op", "alarm", "ok", "persist", "enabled",
             "onunknown", "when", "to", "cc", "ctx", "msg"))

# Rule states. NORM and ALARM are the two that matter; UNKNOWN is separate
# because "the cooling is fine" and "nobody can tell me about the cooling" are
# different pieces of news and deserve different subject lines.
NORM, ALARM, UNKNOWN, PAUSED = "NORM", "ALARM", "UNKNOWN", "PAUSED"

# GATED: the rule is fine but not worth watching right now, because the thing
# it protects is switched off. Cooling water for the VSM magnet is normally
# shut when the supply is off, so an alarm then would be noise. Distinct from
# PAUSED, which is a person deciding to be quiet; this is the plant deciding.
GATED = "GATED"


def _split(text):
    return [p.strip() for p in (text or "").split(",") if p.strip()]


class Rule(object):
    """One line of the Rules property, parsed, plus its running state."""

    def __init__(self, line):
        # msg= swallows the rest of the line, so it must come last. Everything
        # else is order-free.
        self.raw = line
        pos = line.find("msg=")
        if pos >= 0:
            self.msg = line[pos + 4:].strip()
            head = line[:pos]
        else:
            self.msg = ""
            head = line

        fields = {}
        for token in head.split():
            if "=" not in token:
                raise ValueError("%r is not key=value" % token)
            key, _, value = token.partition("=")
            if key not in _KEYS:
                raise ValueError("unknown field %r" % key)
            fields[key] = value

        self.name = fields.get("name", "")
        if not self.name:
            raise ValueError("no name=")
        if not self.msg:
            self.msg = self.name

        self.op = fields.get("op", "state")
        if self.op not in ("state", "edge"):
            raise ValueError("op must be state or edge, not %r" % self.op)

        self.dev = fields.get("dev", "")
        self.attr = fields.get("attr", "")
        if self.op == "state" and not self.dev:
            raise ValueError("op=state needs dev=")
        if self.op == "edge":
            if "/" not in self.attr or self.attr.count("/") != 3:
                raise ValueError("op=edge needs attr=domain/family/member/attr")
            self.dev, _, self.attrname = self.attr.rpartition("/")

        self.alarm = set(s.upper() for s in
                         _split(fields.get("alarm", "ALARM,FAULT")))
        self.ok = set(s.upper() for s in _split(fields.get("ok", "ON")))
        overlap = self.alarm & self.ok
        if overlap:
            raise ValueError("%s is in both alarm= and ok="
                             % ",".join(sorted(overlap)))

        try:
            self.persist = int(fields.get("persist", "2"))
        except ValueError:
            raise ValueError("persist must be an integer")
        if self.persist < 1:
            raise ValueError("persist must be at least 1")

        self.enabled = fields.get("enabled", "yes").lower() not in ("no",
                                                                    "false",
                                                                    "0")
        self.onunknown = fields.get("onunknown", "alarm").lower()
        if self.onunknown not in ("alarm", "ignore"):
            raise ValueError("onunknown must be alarm or ignore")

        # when=device:STATE[,STATE] -- evaluate this rule only while that
        # device is in one of those states.
        self.whendev = ""
        self.whenstates = set()
        gate = fields.get("when", "")
        if gate:
            dev, sep, states = gate.partition(":")
            if not sep or not dev or not states:
                raise ValueError("when= must be device:STATE[,STATE]")
            if "/" not in dev:
                raise ValueError("when= needs a device name, got %r" % dev)
            self.whendev = dev
            self.whenstates = set(x.upper() for x in _split(states))
            if not self.whenstates:
                raise ValueError("when= lists no states")

        self.to = _split(fields.get("to", ""))
        self.cc = _split(fields.get("cc", ""))
        self.ctx = _split(fields.get("ctx", ""))

        self.reset_runtime()

    def reset_runtime(self):
        self.state = NORM
        self.pending = 0
        self.unknown = 0
        self.lastvalue = ""
        self.lastcount = None          # op=edge
        self.since = 0.0               # when the current state was entered
        self.lastmail = 0.0            # last reminder
        self.acked = False
        self.snoozeuntil = 0.0
        self.proxy = None
        self.gateproxy = None
        self.gatevalue = ""

    def snoozed(self, now):
        return self.snoozeuntil > now

    def recipients(self, default):
        # to= replaces the default list, cc= adds to it. Both at once means
        # to= won and cc= extends that.
        base = list(self.to) if self.to else list(default)
        for a in self.cc:
            if a not in base:
                base.append(a)
        return base


# PROTECTED REGION END #    //  AlarmNotifier.additionnal_import

__all__ = ["AlarmNotifier", "main"]


class AlarmNotifier(Device):
    """
    Watches the State of other device servers and sends e-mail.
    """
    # PROTECTED REGION ID(AlarmNotifier.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  AlarmNotifier.class_variable

    # -----------------
    # Device Properties
    # -----------------

    Rules = device_property(
        dtype=('str',),
        doc="One rule per element, as key=value pairs. msg= must come last "
            "because it swallows the rest of the line. Blank lines and lines "
            "starting with # are ignored.\n"
            "Fields: name (required), dev or attr, op=state|edge, alarm=, "
            "ok=, persist=, enabled=, onunknown=, to=, cc=, ctx=, msg=.",
    )

    Recipients = device_property(
        dtype=('str',),
        doc="Default destination addresses.",
    )

    PollPeriod = device_property(
        dtype='double', default_value=10.0,
        doc="Seconds between sweeps. No point going faster: whatever had to "
            "react already did, in the interlock.",
    )

    ProxyTimeout = device_property(
        dtype='int', default_value=1500,
        doc="Milliseconds a State read may block for. With everything down, a "
            "sweep costs this times the number of rules, which is why the "
            "sweep runs in its own thread.",
    )

    UnknownCycles = device_property(
        dtype='int', default_value=30,
        doc="Sweeps a device may be unreadable before it is reported. The "
            "default times the default PollPeriod is five minutes, which "
            "absorbs a Starter restart or a Pi reboot without mail.",
    )

    ReminderHours = device_property(
        dtype='double', default_value=24.0,
        doc="Repeat mail while an alarm is still active. 0 disables. "
            "Acknowledge silences it for one alarm without disabling it.",
    )

    ReportSchedule = device_property(
        dtype='str', default_value="mon 08:00",
        doc="Periodic status mail: 'daily 07:30', 'mon 08:00', "
            "'mon,thu 08:00'. Empty disables it. This is the only thing that "
            "tells you this server is still alive, so think before emptying "
            "it.",
    )

    SubjectPrefix = device_property(dtype='str', default_value="[SURFMOSS]")

    SendmailPath = device_property(
        dtype='str', default_value="/usr/sbin/sendmail",
        doc="msmtp's sendmail. Using it rather than smtplib keeps the "
            "credentials in /etc/msmtprc and out of the Tango database.",
    )

    SendTimeout = device_property(dtype='int', default_value=30)

    MaxSnoozeHours = device_property(
        dtype='double', default_value=24.0,
        doc="Cap on the Snooze command. Silencing a rule for longer means "
            "editing enabled=no in Jive, which leaves a trace and shows up in "
            "the weekly report. The friction is the point.",
    )

    # ----------
    # Attributes
    # ----------

    UpdateCount = attribute(dtype='int', label="UpdateCount")
    ActiveCount = attribute(dtype='int', label="ActiveCount")
    ActiveAlarms = attribute(dtype=('str',), max_dim_x=128,
                             label="ActiveAlarms")
    RuleStates = attribute(dtype=('str',), max_dim_x=128, label="RuleStates")
    SnoozedRules = attribute(dtype=('str',), max_dim_x=128,
                             label="SnoozedRules")
    DisabledRules = attribute(dtype=('str',), max_dim_x=128,
                              label="DisabledRules")
    GatedRules = attribute(dtype=('str',), max_dim_x=128, label="GatedRules",
                           doc="Rules held because the equipment they watch "
                               "is switched off, with the gate device and the "
                               "state it reported.")
    LastAlarm = attribute(dtype='str', label="LastAlarm")
    LastAlarmTime = attribute(dtype='str', label="LastAlarmTime")
    LastMailTime = attribute(dtype='str', label="LastMailTime")
    LastMailError = attribute(dtype='str', label="LastMailError")
    MailQueue = attribute(dtype='int', label="MailQueue")
    SnoozeState = attribute(
        dtype='str', access=AttrWriteType.READ_WRITE, memorized=True,
        hw_memorized=True, display_level=DispLevel.EXPERT,
        label="SnoozeState",
        doc="JSON of the live snoozes, kept memorized so they survive a "
            "restart of this server. Not meant to be edited by hand.",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(AlarmNotifier.init_device) ENABLED START #
        self.stop_event = threading.Event()
        self.stop_event.set()
        self.sweeploop = None
        self.mailloop = None

        self.lock = threading.Lock()
        self.mailq = queue.Queue()
        self.rules = []
        self.updatecount = 0
        self.lastalarm = ""
        self.lastalarmtime = "never"
        self.lastmailtime = "never"
        self.lastmailerror = ""
        self.lastreport = ""
        self.pendingsnoozes = getattr(self, "pendingsnoozes", "")

        problems = self.load_rules()
        if problems:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Bad rules:\n  " + "\n  ".join(problems))
            return

        if not self.Recipients:
            self.set_state(tango.DevState.FAULT)
            self.set_status("No Recipients: this server would watch "
                            "everything and tell nobody")
            return

        self.apply_snoozes(self.pendingsnoozes)

        self.set_state(tango.DevState.ON)
        self.set_status("%d rules, %d enabled" %
                        (len(self.rules),
                         len([r for r in self.rules if r.enabled])))

        self.stop_event.clear()
        self.mailloop = threading.Thread(target=self.mail_thread,
                                         name="AlarmNotifier-mail")
        self.mailloop.daemon = True
        self.mailloop.start()
        self.sweeploop = threading.Thread(target=self.sweep_thread,
                                          name="AlarmNotifier-sweep")
        self.sweeploop.daemon = True
        self.sweeploop.start()
        # PROTECTED REGION END #    //  AlarmNotifier.init_device

    # PROTECTED REGION ID(AlarmNotifier.protected_methods) ENABLED START #

    # --- configuration ------------------------------------------------------

    def load_rules(self):
        """Parse the Rules property. Returns a list of complaints; an empty
        list means every rule parsed."""
        rules, problems, seen = [], [], set()
        for line in (self.Rules or []):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                rule = Rule(line)
            except ValueError as exc:
                problems.append("%s: %s" % (line[:40], exc))
                continue
            if rule.name in seen:
                problems.append("%s: duplicate name" % rule.name)
                continue
            seen.add(rule.name)
            rules.append(rule)
        if not problems:
            self.rules = rules
        return problems

    def find(self, name):
        for rule in self.rules:
            if rule.name == name:
                return rule
        raise tango.DevFailed("No rule called %r" % name)

    def apply_snoozes(self, blob):
        try:
            data = json.loads(blob) if blob else {}
        except ValueError:
            return
        now = time.time()
        for name, until in data.items():
            try:
                rule = self.find(name)
            except Exception:
                continue                  # rule renamed or removed since
            if until > now:
                rule.snoozeuntil = until

    def save_snoozes(self):
        now = time.time()
        data = dict((r.name, r.snoozeuntil) for r in self.rules
                    if r.snoozeuntil > now)
        self.pendingsnoozes = json.dumps(data)
        return self.pendingsnoozes

    # --- the sweep ----------------------------------------------------------

    def sweep_thread(self):
        while not self.stop_event.wait(self.PollPeriod):
            try:
                self.sweep()
            except Exception as exc:
                # A bad sweep must not kill the loop: the loop stopping is the
                # one failure this server cannot report on itself.
                self.error_stream("sweep failed: %s" % exc)
                self.set_state(tango.DevState.FAULT)
                self.set_status("Sweep failed: %s" % exc)

    def sweep(self):
        now = time.time()
        for rule in self.rules:
            if not rule.enabled:
                rule.state = PAUSED
                continue
            if rule.snoozed(now):
                rule.state = PAUSED
                continue
            if rule.state == PAUSED:       # woke up; start from a clean slate
                self.restart(rule)

            if rule.whendev and not self.gate_open(rule):
                if rule.state != GATED:
                    # No RESUELTO mail on the way in: shutting the thing down
                    # is a fair way to end the problem, but nothing was
                    # repaired, and a "resolved" mail would say otherwise.
                    rule.state = GATED
                    rule.pending = 0
                    rule.unknown = 0
                    rule.acked = False
                continue
            if rule.state == GATED:
                self.restart(rule)

            try:
                if rule.op == "edge":
                    self.check_edge(rule, now)
                else:
                    self.check_state(rule, now)
            except Exception as exc:
                self.error_stream("rule %s: %s" % (rule.name, exc))

        self.remind(now)
        self.maybe_report(now)

        with self.lock:
            self.updatecount += 1
        active = [r for r in self.rules if r.state in (ALARM, UNKNOWN)]
        if self.get_state() != tango.DevState.FAULT or not self.lastmailerror:
            if active:
                self.set_state(tango.DevState.ALARM)
                self.set_status("Active: " +
                                ", ".join(r.name for r in active))
            else:
                self.set_state(tango.DevState.ON)
                paused = len([r for r in self.rules if r.state == PAUSED])
                self.set_status("All clear (%d rules, %d paused)"
                                % (len(self.rules), paused))

    def restart(self, rule):
        """Begin evaluating a rule from scratch.

        Used when a gate opens or a snooze ends. Starting at NORM rather than
        inheriting is what catches the case that matters: the water was
        already off, someone switches the magnet on, and the rule has to
        notice a condition that was true before it was allowed to look.
        Resetting lastcount stops an op=edge rule firing over a counter that
        moved while nobody was watching.
        """
        rule.state = NORM
        rule.pending = 0
        rule.unknown = 0
        rule.lastcount = None

    def gate_proxy(self, rule):
        if rule.gateproxy is None:
            rule.gateproxy = tango.DeviceProxy(rule.whendev)
            rule.gateproxy.set_timeout_millis(self.ProxyTimeout)
        return rule.gateproxy

    def gate_open(self, rule):
        """True when the rule should be evaluated.

        An unreadable gate counts as open. Failing towards a mail you did not
        need is recoverable; failing towards silence because the gate device
        happened to be down is how the one alarm that mattered gets lost.
        """
        try:
            current = str(self.gate_proxy(rule).state())
        except Exception as exc:
            rule.gateproxy = None
            rule.gatevalue = "unreadable: %s" % exc
            return True
        rule.gatevalue = current
        return current.upper() in rule.whenstates

    def proxy_for(self, rule):
        if rule.proxy is None:
            rule.proxy = tango.DeviceProxy(rule.dev)
            rule.proxy.set_timeout_millis(self.ProxyTimeout)
        return rule.proxy

    def check_state(self, rule, now):
        try:
            current = str(self.proxy_for(rule).state())
        except Exception as exc:
            rule.proxy = None
            rule.unknown += 1
            if (rule.onunknown == "alarm" and rule.state != UNKNOWN
                    and rule.unknown >= self.UnknownCycles):
                self.enter(rule, UNKNOWN, now,
                           "%s cannot be read (%d sweeps): %s"
                           % (rule.dev, rule.unknown, exc))
            return

        was = rule.state
        rule.unknown = 0
        rule.lastvalue = current
        if was == UNKNOWN:
            self.enter(rule, NORM, now,
                       "%s answers again, State = %s" % (rule.dev, current))
            # Fall through: it may answer and still be in alarm.
            was = NORM

        if current.upper() in rule.alarm:
            rule.pending += 1
            if was != ALARM and rule.pending >= rule.persist:
                self.enter(rule, ALARM, now,
                           "%s State = %s" % (rule.dev, current))
        elif current.upper() in rule.ok:
            rule.pending = 0
            if was == ALARM:
                self.enter(rule, NORM, now,
                           "%s State = %s" % (rule.dev, current))
        # Any other state is transitional: hold, neither trip nor recover.
        # This is what keeps an Init from Jive out of your inbox.

    def check_edge(self, rule, now):
        try:
            reading = self.proxy_for(rule).read_attribute(rule.attrname)
            if reading.quality == tango.AttrQuality.ATTR_INVALID:
                raise ValueError("attribute quality is INVALID")
            value = int(reading.value)
        except Exception as exc:
            rule.proxy = None
            rule.unknown += 1
            if (rule.onunknown == "alarm" and rule.state != UNKNOWN
                    and rule.unknown >= self.UnknownCycles):
                self.enter(rule, UNKNOWN, now,
                           "%s cannot be read (%d sweeps): %s"
                           % (rule.attr, rule.unknown, exc))
            return

        rule.unknown = 0
        if rule.state == UNKNOWN:
            rule.state = NORM
        rule.lastvalue = str(value)

        if rule.lastcount is None:
            rule.lastcount = value          # first sweep: adopt, do not fire
            return
        if value > rule.lastcount:
            self.notify(rule, "AVISO", "%s went from %d to %d"
                        % (rule.attr, rule.lastcount, value), now)
        elif value < rule.lastcount:
            # A counter that went backwards means the publisher restarted,
            # which is itself worth knowing: something over there died.
            self.notify(rule, "AVISO", "%s went backwards, %d to %d: the "
                        "device was restarted"
                        % (rule.attr, rule.lastcount, value), now)
        rule.lastcount = value

    def enter(self, rule, state, now, detail):
        rule.state = state
        rule.since = now
        rule.pending = 0
        rule.acked = False
        rule.lastmail = now
        if state == ALARM:
            self.lastalarm = rule.name
            self.lastalarmtime = time.strftime("%Y-%m-%d %H:%M:%S")
            self.notify(rule, "ALARMA", detail, now)
        elif state == UNKNOWN:
            self.lastalarm = rule.name
            self.lastalarmtime = time.strftime("%Y-%m-%d %H:%M:%S")
            self.notify(rule, "SIN LECTURA", detail, now)
        else:
            self.notify(rule, "RESUELTO", detail, now)

    def remind(self, now):
        if self.ReminderHours <= 0:
            return
        gap = self.ReminderHours * 3600.0
        for rule in self.rules:
            if rule.state not in (ALARM, UNKNOWN) or rule.acked:
                continue
            if now - rule.lastmail < gap:
                continue
            rule.lastmail = now
            hours = (now - rule.since) / 3600.0
            self.notify(rule, "SIGUE",
                        "still %s after %.1f h" % (rule.state, hours), now)

    # --- mail ---------------------------------------------------------------

    def notify(self, rule, tag, detail, now):
        body = ["Regla:    %s" % rule.name,
                "Device:   %s" % rule.dev,
                "Estado:   %s" % rule.state,
                "Hora:     %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
                "",
                detail]
        if rule.ctx:
            body.append("")
            body.append("Contexto:")
            for full in rule.ctx:
                body.append("  %s = %s" % (full, self.read_context(full)))
        self.queue_mail(rule.recipients(self.Recipients),
                        "%s %s — %s" % (self.SubjectPrefix, tag, rule.msg),
                        "\n".join(body))

    def read_context(self, full):
        """Read one domain/family/member/attribute for the mail body. A
        context attribute that cannot be read says so; it is never left out
        silently, or the mail would quietly lose the number you wanted."""
        try:
            dev, _, attr = full.rpartition("/")
            proxy = tango.DeviceProxy(dev)
            proxy.set_timeout_millis(self.ProxyTimeout)
            reading = proxy.read_attribute(attr)
            if reading.quality == tango.AttrQuality.ATTR_INVALID:
                return "<INVALID>"
            return "%s" % (reading.value,)
        except Exception as exc:
            return "<no se pudo leer: %s>" % exc

    def queue_mail(self, to, subject, body):
        if not to:
            self.lastmailerror = "no recipients"
            return
        self.mailq.put((to, subject, body))

    def mail_thread(self):
        while True:
            try:
                item = self.mailq.get(timeout=1.0)
            except queue.Empty:
                if self.stop_event.is_set():
                    return
                continue
            to, subject, body = item
            try:
                self.send_mail(to, subject, body)
                self.lastmailtime = time.strftime("%Y-%m-%d %H:%M:%S")
                self.lastmailerror = ""
            except Exception as exc:
                self.lastmailerror = "%s" % exc
                self.error_stream("cannot send mail: %s" % exc)
                self.set_state(tango.DevState.FAULT)
                self.set_status("Cannot send mail: %s" % exc)
                # Put it back and slow down, rather than dropping the one
                # message that mattered.
                self.mailq.put(item)
                if self.stop_event.wait(30.0):
                    return

    def send_mail(self, to, subject, body):
        message = ("To: %s\r\n"
                   "Subject: %s\r\n"
                   "Content-Type: text/plain; charset=UTF-8\r\n"
                   "\r\n%s\r\n" % (", ".join(to), subject, body))
        proc = subprocess.Popen([self.SendmailPath, "-t"],
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        try:
            out, err = proc.communicate(message.encode("utf-8"),
                                        timeout=self.SendTimeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise RuntimeError("%s timed out after %d s"
                               % (self.SendmailPath, self.SendTimeout))
        if proc.returncode != 0:
            raise RuntimeError("%s exited %d: %s"
                               % (self.SendmailPath, proc.returncode,
                                  err.decode("utf-8", "replace").strip()))

    # --- periodic report ----------------------------------------------------

    def maybe_report(self, now):
        if not self.ReportSchedule:
            return
        try:
            when, _, clock = self.ReportSchedule.strip().partition(" ")
            hour, _, minute = clock.partition(":")
            hour, minute = int(hour), int(minute)
        except ValueError:
            return
        local = time.localtime(now)
        stamp = time.strftime("%Y-%m-%d", local)
        if self.lastreport == stamp:
            return
        if when.lower() != "daily":
            days = set(_DAYS.get(d.strip().lower(), -1)
                       for d in when.split(","))
            if local.tm_wday not in days:
                return
        if (local.tm_hour, local.tm_min) < (hour, minute):
            return
        self.lastreport = stamp
        self.queue_mail(list(self.Recipients),
                        "%s ESTADO — %s" % (self.SubjectPrefix,
                                            self.report_text().splitlines()[0]),
                        self.report_text())

    def report_text(self):
        now = time.time()
        active = [r for r in self.rules if r.state in (ALARM, UNKNOWN)]
        head = ("%d alarma(s) activa(s)" % len(active)) if active \
            else "Todo correcto"
        lines = [head, "",
                 "%-18s %-34s %-8s %s" % ("REGLA", "DEVICE", "ESTADO",
                                          "ULTIMO VALOR")]
        for rule in self.rules:
            lines.append("%-18s %-34s %-8s %s"
                         % (rule.name, rule.dev, rule.state,
                            rule.lastvalue or "-"))

        snoozed = [r for r in self.rules if r.snoozed(now)]
        if snoozed:
            lines += ["", "Dormidas:"]
            for rule in snoozed:
                lines.append("  %-18s despierta en %.1f h"
                             % (rule.name, (rule.snoozeuntil - now) / 3600.0))

        gated = [r for r in self.rules if r.state == GATED]
        if gated:
            lines += ["", "En espera (el equipo vigilado esta apagado):"]
            for rule in gated:
                lines.append("  %-18s %s = %s"
                             % (rule.name, rule.whendev, rule.gatevalue))

        off = [r for r in self.rules if not r.enabled]
        if off:
            lines += ["", "Deshabilitadas (enabled=no en Jive):"]
            for rule in off:
                lines.append("  %-18s %s" % (rule.name, rule.msg))

        lines += ["", "Sondeos desde el arranque: %d" % self.updatecount,
                  "Ultimo correo: %s" % self.lastmailtime]
        if self.lastmailerror:
            lines.append("Ultimo error de envio: %s" % self.lastmailerror)
        return "\n".join(lines)

    # PROTECTED REGION END #    //  AlarmNotifier.protected_methods

    def always_executed_hook(self):
        # PROTECTED REGION ID(AlarmNotifier.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  AlarmNotifier.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(AlarmNotifier.delete_device) ENABLED START #
        self.save_snoozes()
        self.stop_event.set()
        for loop in (self.sweeploop, self.mailloop):
            if loop is not None and loop.is_alive():
                loop.join(timeout=2.0 + self.PollPeriod)
        # PROTECTED REGION END #    //  AlarmNotifier.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_UpdateCount(self):
        # PROTECTED REGION ID(AlarmNotifier.UpdateCount_read) ENABLED START #
        return self.updatecount
        # PROTECTED REGION END #    //  AlarmNotifier.UpdateCount_read

    def read_ActiveCount(self):
        # PROTECTED REGION ID(AlarmNotifier.ActiveCount_read) ENABLED START #
        return len([r for r in self.rules if r.state in (ALARM, UNKNOWN)])
        # PROTECTED REGION END #    //  AlarmNotifier.ActiveCount_read

    def read_ActiveAlarms(self):
        # PROTECTED REGION ID(AlarmNotifier.ActiveAlarms_read) ENABLED START #
        return ["%s=%s" % (r.name, r.state) for r in self.rules
                if r.state in (ALARM, UNKNOWN)]
        # PROTECTED REGION END #    //  AlarmNotifier.ActiveAlarms_read

    def read_RuleStates(self):
        # PROTECTED REGION ID(AlarmNotifier.RuleStates_read) ENABLED START #
        return ["%s=%s" % (r.name, r.state) for r in self.rules]
        # PROTECTED REGION END #    //  AlarmNotifier.RuleStates_read

    def read_SnoozedRules(self):
        # PROTECTED REGION ID(AlarmNotifier.SnoozedRules_read) ENABLED START #
        now = time.time()
        return ["%s=%.1f h" % (r.name, (r.snoozeuntil - now) / 3600.0)
                for r in self.rules if r.snoozed(now)]
        # PROTECTED REGION END #    //  AlarmNotifier.SnoozedRules_read

    def read_DisabledRules(self):
        # PROTECTED REGION ID(AlarmNotifier.DisabledRules_read) ENABLED START #
        return ["%s" % r.name for r in self.rules if not r.enabled]
        # PROTECTED REGION END #    //  AlarmNotifier.DisabledRules_read

    def read_GatedRules(self):
        # PROTECTED REGION ID(AlarmNotifier.GatedRules_read) ENABLED START #
        return ["%s=%s:%s" % (r.name, r.whendev, r.gatevalue)
                for r in self.rules if r.state == GATED]
        # PROTECTED REGION END #    //  AlarmNotifier.GatedRules_read

    def read_LastAlarm(self):
        # PROTECTED REGION ID(AlarmNotifier.LastAlarm_read) ENABLED START #
        return self.lastalarm
        # PROTECTED REGION END #    //  AlarmNotifier.LastAlarm_read

    def read_LastAlarmTime(self):
        # PROTECTED REGION ID(AlarmNotifier.LastAlarmTime_read) ENABLED START #
        return self.lastalarmtime
        # PROTECTED REGION END #    //  AlarmNotifier.LastAlarmTime_read

    def read_LastMailTime(self):
        # PROTECTED REGION ID(AlarmNotifier.LastMailTime_read) ENABLED START #
        return self.lastmailtime
        # PROTECTED REGION END #    //  AlarmNotifier.LastMailTime_read

    def read_LastMailError(self):
        # PROTECTED REGION ID(AlarmNotifier.LastMailError_read) ENABLED START #
        return self.lastmailerror
        # PROTECTED REGION END #    //  AlarmNotifier.LastMailError_read

    def read_MailQueue(self):
        # PROTECTED REGION ID(AlarmNotifier.MailQueue_read) ENABLED START #
        return self.mailq.qsize()
        # PROTECTED REGION END #    //  AlarmNotifier.MailQueue_read

    def read_SnoozeState(self):
        # PROTECTED REGION ID(AlarmNotifier.SnoozeState_read) ENABLED START #
        return self.save_snoozes()
        # PROTECTED REGION END #    //  AlarmNotifier.SnoozeState_read

    def write_SnoozeState(self, value):
        # PROTECTED REGION ID(AlarmNotifier.SnoozeState_write) ENABLED START #
        # Tango replays the memorized value at start-up, which may land before
        # or after init_device has parsed the rules. Keep the blob either way
        # and apply what can be applied now.
        self.pendingsnoozes = value
        if getattr(self, "rules", None):
            self.apply_snoozes(value)
        # PROTECTED REGION END #    //  AlarmNotifier.SnoozeState_write

    # --------
    # Commands
    # --------

    def do_snooze(self, name, hours):
        """Shared by Snooze and SnoozeFor, so the cap is checked in one place
        and cannot drift between the two entry points."""
        rule = self.find(name)
        try:
            hours = float(hours)
        except (TypeError, ValueError):
            raise ValueError("%r is not a number of hours" % (hours,))
        if hours <= 0:
            raise ValueError("hours must be positive; use Wake to cancel")
        if hours > self.MaxSnoozeHours:
            raise ValueError("at most %g h; to silence a rule for longer, set "
                             "enabled=no in Jive, where it leaves a trace and "
                             "shows up in the weekly report"
                             % self.MaxSnoozeHours)
        rule.snoozeuntil = time.time() + hours * 3600.0
        rule.state = PAUSED
        self.save_snoozes()
        return "%s asleep for %g h" % (rule.name, hours)

    @command(dtype_in=('str',),
             doc_in="[rule name, hours]")
    @DebugIt()
    def Snooze(self, argin):
        # PROTECTED REGION ID(AlarmNotifier.Snooze) ENABLED START #
        if len(argin) != 2:
            raise ValueError("Snooze takes [name, hours]")
        self.do_snooze(argin[0], argin[1])
        # PROTECTED REGION END #    //  AlarmNotifier.Snooze

    @command(dtype_in='str', dtype_out='str',
             doc_in="rule name and hours, e.g. 'mossCompresor 8'",
             doc_out="what was done")
    @DebugIt()
    def SnoozeFor(self, argin):
        # PROTECTED REGION ID(AlarmNotifier.SnoozeFor) ENABLED START #
        # Same thing as Snooze with a scalar argument. ATKPanel will not offer
        # a command taking DevVarStringArray, so from the generic panel -- the
        # only interface most people in the lab will open -- Snooze is
        # unreachable. This one shows up as a text field.
        parts = argin.split()
        if len(parts) != 2:
            raise ValueError("expected 'rulename hours', e.g. "
                             "'mossCompresor 8', got %r" % argin)
        return self.do_snooze(parts[0], parts[1])
        # PROTECTED REGION END #    //  AlarmNotifier.SnoozeFor

    @command(dtype_in='str', doc_in="rule name")
    @DebugIt()
    def Wake(self, argin):
        # PROTECTED REGION ID(AlarmNotifier.Wake) ENABLED START #
        rule = self.find(argin)
        rule.snoozeuntil = 0.0
        rule.state = NORM
        rule.pending = 0
        rule.unknown = 0
        self.save_snoozes()
        # PROTECTED REGION END #    //  AlarmNotifier.Wake

    @command(dtype_in='str', doc_in="rule name")
    @DebugIt()
    def Acknowledge(self, argin):
        # PROTECTED REGION ID(AlarmNotifier.Acknowledge) ENABLED START #
        # Silences the reminders only. The alarm stays active and visible: an
        # acknowledged alarm is one you have seen, not one that has gone away.
        self.find(argin).acked = True
        # PROTECTED REGION END #    //  AlarmNotifier.Acknowledge

    @command()
    @DebugIt()
    def AcknowledgeAll(self):
        # PROTECTED REGION ID(AlarmNotifier.AcknowledgeAll) ENABLED START #
        for rule in self.rules:
            rule.acked = True
        # PROTECTED REGION END #    //  AlarmNotifier.AcknowledgeAll

    @command(dtype_out='str')
    @DebugIt()
    def Report(self):
        # PROTECTED REGION ID(AlarmNotifier.Report) ENABLED START #
        return self.report_text()
        # PROTECTED REGION END #    //  AlarmNotifier.Report

    @command()
    @DebugIt()
    def TestMail(self):
        # PROTECTED REGION ID(AlarmNotifier.TestMail) ENABLED START #
        self.queue_mail(list(self.Recipients),
                        "%s PRUEBA" % self.SubjectPrefix,
                        self.report_text())
        # PROTECTED REGION END #    //  AlarmNotifier.TestMail

    @command(dtype_in=('str',), doc_in="[subject, body]")
    @DebugIt()
    def SendMessage(self, argin):
        # PROTECTED REGION ID(AlarmNotifier.SendMessage) ENABLED START #
        # For a person at a keyboard or an end-of-run script. Do NOT call this
        # from the loop of a safety device server: that would put an SMTP
        # client inside a protection path, and if this server is down the
        # caller ends in FAULT over an e-mail. If something needs to raise an
        # alarm, give it a State and add a rule.
        if len(argin) != 2:
            raise ValueError("SendMessage takes [subject, body]")
        self.queue_mail(list(self.Recipients),
                        "%s %s" % (self.SubjectPrefix, argin[0]), argin[1])
        # PROTECTED REGION END #    //  AlarmNotifier.SendMessage

    @command(dtype_out='str')
    @DebugIt()
    def ReloadRules(self):
        # PROTECTED REGION ID(AlarmNotifier.ReloadRules) ENABLED START #
        # Re-read Rules without an Init, keeping the running state of every
        # rule whose name survived. An Init would lose which alarms were
        # already acknowledged and re-mail all of them.
        old = dict((r.name, r) for r in self.rules)
        self.Rules = tango.Database().get_device_property(
            self.get_name(), "Rules")["Rules"]
        problems = self.load_rules()
        if problems:
            return "Not reloaded:\n  " + "\n  ".join(problems)
        for rule in self.rules:
            previous = old.get(rule.name)
            if previous is not None and previous.raw == rule.raw:
                rule.state = previous.state
                rule.pending = previous.pending
                rule.unknown = previous.unknown
                rule.lastvalue = previous.lastvalue
                rule.lastcount = previous.lastcount
                rule.since = previous.since
                rule.lastmail = previous.lastmail
                rule.acked = previous.acked
                rule.snoozeuntil = previous.snoozeuntil
                rule.gatevalue = previous.gatevalue
        return "%d rules loaded, %d enabled" % (
            len(self.rules), len([r for r in self.rules if r.enabled]))
        # PROTECTED REGION END #    //  AlarmNotifier.ReloadRules

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(AlarmNotifier.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((AlarmNotifier,), args=args, **kwargs)
    # PROTECTED REGION END #    //  AlarmNotifier.main


if __name__ == '__main__':
    main()
