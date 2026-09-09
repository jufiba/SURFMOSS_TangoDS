# -*- coding: utf-8 -*-
#
# This file is part of the AnalogInterlock project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" AnalogInterlock

Generic threshold interlock between two Tango devices: reads a numeric
attribute from an input device and asserts or de-asserts a permissive on an
output device.

The permissive is granted at ThresholdOn and withdrawn at ThresholdOff, with
the band between them as hysteresis. Which way round that is depends on
Reverse: normally the quantity must stay *high* (a flow, a supply pressure)
and ThresholdOff is the lower of the two; with Reverse it must stay *low* (a
temperature, a chamber pressure) and ThresholdOff is the higher. The direction
is a declared property and not inferred from the two numbers, so a pair
entered the wrong way round is still caught at start-up instead of quietly
inverting the interlock.

With WatchOnly the server commands nothing and only reports: Permit and the
state are then a judgement about the input for something else to act on --
AlarmNotifier, a synoptic -- which is what the `<instrument>/warn/` domain
means. It too is declared rather than inferred from an empty OutputDevice: a
`safety/` device whose OutputDevice property went missing must fault, not
quietly downgrade itself to watching.

This is a *secondary* protection layer. It runs in userspace, over CORBA,
between two processes on a Raspberry Pi. Anything that genuinely must not
happen belongs in a hardware chain — a flow switch in series with the supply
enable — not here.

Failure modes and what this server does about each:

  input past ThresholdOff     -> de-assert, ALARM
  input attribute unreadable  -> de-assert after MaxReadFailures, FAULT
  input attribute INVALID     -> counted as a read failure
  input publisher frozen      -> de-assert after StaleCycles, ALARM
                                 (detected via HeartbeatAttribute; a frozen
                                 publisher keeps returning its last good value,
                                 which is otherwise indistinguishable from a
                                 healthy reading)
  this server dies            -> keepalives stop; the output device's own
                                 deadman de-asserts. Not handled here, by
                                 construction: a process cannot be its own
                                 watchdog.
  output device unreachable   -> FAULT; nothing else is possible from here
  output command refused      -> FAULT, and the permissive is not granted. The
                                 status says which command failed and why
  gate outside GateStates     -> OFF, not evaluating; a latched trip is held,
                                 LastTrip* is left alone
  gate unreadable             -> evaluated anyway (fail towards acting); the
                                 status says the gate could not be read
  bad gate configuration      -> refused at start-up, the status names the value
  bypassed (BypassFor)        -> DISABLE, or STANDBY in the last
                                 BypassWarnMinutes; no trip command, LastTrip*
                                 untouched, Keepalive still sent for a deadman.
                                 Expires on its own and re-evaluates from clean
  this server stops sweeping  -> for the permissive shape the output's deadman
                                 fires; for the command-on-trip shape nothing
                                 does. UpdateCount is there for an AlarmNotifier
                                 rule to catch it
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
# PROTECTED REGION ID(AnalogInterlock.additionnal_import) ENABLED START #
import os
import sys
import json
import time
import threading


class ControlThread(threading.Thread):
    """Polls the input and maintains the permissive."""

    def __init__(self, ds):
        threading.Thread.__init__(self, name="AnalogInterlock-ctrl")
        self.daemon = True
        self.ds = ds

    def run(self):
        ds = self.ds
        try:
            while not ds.stop_event.wait(ds.PollPeriod):
                try:
                    ds.cycle()
                except Exception as exc:
                    # A cycle must never kill the loop; the loop stopping is
                    # itself the dangerous condition.
                    ds.trip("internal error: %s" % exc, tango.DevState.FAULT)
        except Exception as exc:
            ds.trip("control thread died: %s" % exc, tango.DevState.FAULT)


# PROTECTED REGION END #    //  AnalogInterlock.additionnal_import

__all__ = ["AnalogInterlock", "main"]


class AnalogInterlock(Device):
    """
    Generic threshold interlock between two Tango devices.
    """
    # PROTECTED REGION ID(AnalogInterlock.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  AnalogInterlock.class_variable

    # -----------------
    # Device Properties
    # -----------------

    InputDevice = device_property(
        dtype='str',
        doc="Device to read the measured quantity from, e.g. xps/safety/water",
    )

    InputAttribute = device_property(
        dtype='str', default_value="channel0",
        doc="Attribute to read. Prefer a named attribute (e.g. 'xraygun') "
            "over a positional one (e.g. 'channel0'): if the channel order is "
            "ever changed, a named attribute disappears and this server "
            "faults, whereas a positional one silently starts watching a "
            "different line.",
    )

    HeartbeatAttribute = device_property(
        dtype='str', default_value="UpdateCount",
        doc="Monotonic counter on the input device that advances once per "
            "acquisition cycle. Empty string disables staleness detection.",
    )

    GateDevice = device_property(
        dtype='str', default_value="",
        doc="Device whose state decides whether this interlock evaluates at "
            "all. Empty (the default) means always evaluate, exactly as "
            "before this property existed -- this is the P2 lens and XPS "
            "configuration and it must not shift. Set it to what the "
            "interlock protects: for leem/safety/interlockhv1 that is "
            "leem/power/hv1, so that while the supply is off the resting "
            "state of a command-on-trip interlock -- input on the unsafe "
            "side because the cooling is deliberately closed -- is not read "
            "as a trip. Mirrors AlarmNotifier's when= gate.",
    )

    GateStates = device_property(
        dtype='str', default_value="",
        doc="Comma-separated Tango state names that mean the gate is OPEN "
            "and evaluation should run, e.g. 'ON' or 'ON,RUNNING'. Required "
            "when GateDevice is set, and refused at start-up if it names "
            "anything that is not a Tango state. This is the set that means "
            "*open*, not a list of every state the gate device can be in: "
            "for a supply that only reports ON and OFF, listing both leaves "
            "the gate permanently open and silently restores the pre-gating "
            "behaviour.",
    )

    OutputDevice = device_property(
        dtype='str',
        doc="Device holding the permissive, e.g. xps/safety/switchxraygun. "
            "Leave empty only together with WatchOnly.",
    )

    WatchOnly = device_property(
        dtype='bool', default_value=False,
        doc="If True, no command is ever sent: this device only reports "
            "whether the input is within limits, and OutputDevice must be "
            "empty. For a watch under `<instrument>/warn/` whose output is a "
            "warning rather than a permissive.",
    )

    OnCommand = device_property(dtype='str', default_value="On")
    OffCommand = device_property(dtype='str', default_value="Off")

    KeepaliveCommand = device_property(
        dtype='str', default_value="Keepalive",
        doc="Sent on every cycle while the permissive is granted. Empty "
            "string disables keepalives, e.g. if the output device does not "
            "implement a deadman.",
    )

    Reverse = device_property(
        dtype='bool', default_value=False,
        doc="Which side of the thresholds is safe. False: the input must stay "
            "high, as a cooling flow must (granted above ThresholdOn, "
            "withdrawn below ThresholdOff). True: it must stay low, as a "
            "temperature or a pressure must (granted below ThresholdOn, "
            "withdrawn above ThresholdOff).",
    )

    ThresholdOn = device_property(
        dtype='double', default_value=2.0,
        doc="The permissive is granted when the input passes this: rises "
            "above it normally, falls below it with Reverse.",
    )

    ThresholdOff = device_property(
        dtype='double', default_value=1.6,
        doc="The permissive is withdrawn when the input passes back through "
            "this: falls below it normally, rises above it with Reverse. The "
            "gap to ThresholdOn is the hysteresis that stops the relay "
            "chattering around the trip point, so ThresholdOff must be the "
            "lower of the two normally and the higher with Reverse.",
    )

    PollPeriod = device_property(
        dtype='double', default_value=1.0,
        doc="Seconds between cycles. No point polling faster than the input "
            "device's own integration period.",
    )

    MaxReadFailures = device_property(
        dtype='int', default_value=3,
        doc="Consecutive failed or INVALID reads tolerated before tripping. "
            "Absorbs transient CORBA timeouts without leaving the output "
            "asserted through a real outage.",
    )

    StaleCycles = device_property(
        dtype='int', default_value=5,
        doc="Cycles the heartbeat may fail to advance before tripping.",
    )

    Latching = device_property(
        dtype='bool', default_value=False,
        doc="If True, a trip must be cleared with the Reset command before "
            "the permissive can be granted again. Leave False where the "
            "hardware already latches and requires a physical reset button.",
    )

    ReassertCycles = device_property(
        dtype='int', default_value=30,
        doc="Re-send OnCommand every N cycles while granted, in case the "
            "output device was restarted underneath us. 0 disables.",
    )

    ProxyTimeout = device_property(
        dtype='int', default_value=800,
        doc="Milliseconds a read or command may block for. This is what sets "
            "how long a trip takes when the input device hangs rather than "
            "answering: the worst case is "
            "MaxReadFailures * (ProxyTimeout + PollPeriod), so 800 ms with the "
            "other defaults gives about 5 s. Keep that comfortably below the "
            "output device's DeadmanTimeout, or the deadman fires first and "
            "recovery needs a fresh On() instead of just the flow coming back. "
            "The old 3000 ms default gave 12 s, which lost that race.",
    )

    MaxBypassHours = device_property(
        dtype='double', default_value=8.0,
        doc="Cap on a single BypassFor request. A larger request is "
            "refused, not clamped -- on a safety device the number the "
            "operator typed must be the number in force. To bypass for "
            "longer, renew with BypassFor again once the first one is "
            "running; each renewal is a deliberate act with its own reason "
            "and its own record. Mirrors AlarmNotifier's MaxSnoozeHours.",
    )

    BypassWarnMinutes = device_property(
        dtype='double', default_value=30.0,
        doc="Width of the warning window before a bypass expires. Inside it "
            "the state is STANDBY instead of DISABLE, so an AlarmNotifier "
            "rule can mail 'the bypass on interlockhv1 expires at 18:00' "
            "half an hour ahead. A bypass requested for less than this stays "
            "DISABLE for its whole life and never raises the warning.",
    )

    # ----------
    # Attributes
    # ----------

    InputValue = attribute(dtype='double', label="InputValue", format="%6.2f")
    Permit = attribute(dtype='bool', label="Permit")
    Tripped = attribute(dtype='bool', label="Tripped")
    LastTripTime = attribute(dtype='str', label="LastTripTime")
    LastTripValue = attribute(dtype='double', label="LastTripValue", format="%6.2f")
    LastTripReason = attribute(dtype='str', label="LastTripReason")
    ThresholdOnRB = attribute(dtype='double', label="ThresholdOn", format="%6.2f")
    ThresholdOffRB = attribute(dtype='double', label="ThresholdOff", format="%6.2f")
    LatchingRB = attribute(dtype='bool', label="Latching")

    UpdateCount = attribute(
        dtype='int', label="UpdateCount",
        doc="Advances once per poll, gated and bypassed cycles included. A "
            "rule on this catches a sweep thread that has stopped -- the "
            "failure this server cannot report on itself, and for a "
            "command-on-trip interlock the only cover it has for its own "
            "death.")

    Bypassed = attribute(dtype='bool', label="Bypassed")
    BypassRemaining = attribute(dtype='double', label="BypassRemaining",
                                format="%g",
                                doc="Minutes until the bypass expires, 0 when "
                                    "not bypassed.")
    BypassUntil = attribute(dtype='str', label="BypassUntil")
    BypassSince = attribute(dtype='str', label="BypassSince",
                            doc="Start of the first bypass of this run. "
                                "Renewals do not move it.")
    BypassReason = attribute(dtype='str', label="BypassReason")
    BypassRenewals = attribute(dtype='int', label="BypassRenewals")
    BypassState = attribute(
        dtype='str', access=AttrWriteType.READ_WRITE, memorized=True,
        hw_memorized=True, display_level=DispLevel.EXPERT, label="BypassState",
        doc="JSON of the live bypass, kept memorized so it survives a "
            "restart of this server. Not meant to be edited by hand.",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(AnalogInterlock.init_device) ENABLED START #
        self.stop_event = threading.Event()
        self.stop_event.set()
        self.ctrlloop = None
        self.lock = threading.Lock()

        self.inputvalue = float('nan')
        self.permit = False
        self.tripped = False
        self.lasttriptime = "never"
        self.lasttripvalue = float('nan')
        self.lasttripreason = ""

        self.readfailures = 0
        self.beatfailures = 0
        self.stalecount = 0
        self.manuallatch = False
        self.lastheartbeat = None
        self.cyclessincereassert = 0
        self.updatecount = 0

        self.inputproxy = None
        self.outputproxy = None
        self.gateproxy = None

        # Gate: evaluation runs only while GateDevice is in one of
        # GateStates. An empty GateDevice turns all of this off at the first
        # line of cycle(), so the P2 lens and XPS keep today's behaviour to
        # the cycle.
        self.gatestates = set()
        self.gatewasopen = False        # was the gate open on the last cycle?
        self.cleanslate = False         # one-shot: re-evaluate fresh
        #                                 (gate reopen, or a bypass ending)
        self.gatevalue = ""             # last gate state seen, for Status
        self.gatewarn = ""              # standing note: GateStates never gates
        self.gatefault = ""             # standing note: gate device unreadable
        self.everread = False           # has a reading been taken yet?

        # Bypass: a time-limited, self-expiring suspension of the whole
        # interlock, set with BypassFor and ended early with Arm. Outranks
        # the gate. Absolute epoch times, so a restart resumes to the same
        # wall-clock expiry; 0.0 means armed. self.lock guards this block
        # against BypassFor / Arm on a client thread.
        self.bypassuntil = 0.0
        self.bypasssince = 0.0
        self.bypassreason = ""
        self.bypassrenewals = 0
        self.bypassshort = False        # request shorter than the warn window
        self.bypassrestored = ""        # startup note: a stored bypass expired
        self.pendingbypass = getattr(self, "pendingbypass", "")

        # A misconfiguration is refused here rather than at the first cycle,
        # because a server that starts and then behaves as though the
        # thresholds meant something else is worse than one that never starts.
        # The bool properties are checked first, because a bool that did not
        # survive the trip from the database makes every check below it argue
        # about the wrong value.
        for name in ("WatchOnly", "Reverse", "Latching"):
            complaint = self.bool_property_complaint(name, getattr(self, name))
            if complaint:
                return self.misconfigured(complaint)

        output = (self.OutputDevice or "").strip()
        if self.WatchOnly and output:
            return self.misconfigured(
                "WatchOnly is set, but OutputDevice is %s. Watching and "
                "commanding are different jobs; pick one" % output)
        if not self.WatchOnly and not output:
            return self.misconfigured(
                "no OutputDevice, and WatchOnly is not set. If this device is "
                "meant only to report, say so with WatchOnly; an empty "
                "OutputDevice is not taken to mean it, so that a safety "
                "device that loses the property faults instead of quietly "
                "becoming a bystander")
        if self.Reverse and self.ThresholdOff <= self.ThresholdOn:
            return self.misconfigured(
                "with Reverse the input must stay low, so ThresholdOff (%g) "
                "must be above ThresholdOn (%g)"
                % (self.ThresholdOff, self.ThresholdOn))
        if not self.Reverse and self.ThresholdOff >= self.ThresholdOn:
            return self.misconfigured(
                "ThresholdOff (%g) must be below ThresholdOn (%g). If the "
                "input is meant to stay low rather than high, that is Reverse"
                % (self.ThresholdOff, self.ThresholdOn))

        # Gate configuration. Mirrors AlarmNotifier's when=: a device and the
        # set of its states in which this interlock is allowed to evaluate. A
        # bad value is refused, not defaulted -- a typo in a gate that stops
        # a safety device acting is worse than one that stops it starting.
        complaint = self.gate_config()
        if complaint:
            return self.misconfigured(complaint)

        # A bypass that was live when the server stopped is restored; one
        # that has since expired is not -- the server comes up armed and
        # says so. The time cap, not the restart, is what stops a bypass
        # being forgotten, and a Starter restart at 03:00 that silently
        # re-armed would trip the very experiment the bypass protects.
        self.apply_bypass(self.pendingbypass)

        # Deliberately no command is sent here. This server restarting must not
        # by itself disturb a running experiment: the output device keeps
        # whatever state it had, and the first cycle a fraction of a second
        # later decides on the basis of a real reading. If this server stays
        # down, the output device's deadman is what de-asserts the permissive.
        self.set_state(tango.DevState.INIT)
        self.set_status(self.bypassrestored or "Waiting for first reading")

        self.stop_event.clear()
        self.ctrlloop = ControlThread(self)
        self.ctrlloop.start()
        # PROTECTED REGION END #    //  AnalogInterlock.init_device

    # PROTECTED REGION ID(AnalogInterlock.protected_methods) ENABLED START #
    def misconfigured(self, reason):
        """Refuse to start, and say what to correct. The control thread is
        never started, so nothing is polled and nothing is commanded."""
        self.set_state(tango.DevState.FAULT)
        self.set_status(reason)

    def now(self):
        """Wall clock as a single call, so the bypass tests can pin it."""
        return time.time()

    def _stamp(self, epoch):
        """Epoch -> the same 'YYYY-MM-DD HH:MM:SS' the trip fields use."""
        if not epoch:
            return "-"
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))

    def gate_config(self):
        """Parse GateDevice / GateStates. Returns a complaint to refuse
        start-up with, or None. On success fills self.gatestates and, when the
        open-set looks like it names every state the gate device can be in,
        the standing self.gatewarn note. Kept out of init_device so it can be
        exercised without a database, and follows the threshold checks' style:
        the caller turns a non-None return into self.misconfigured()."""
        gatedev = (self.GateDevice or "").strip()
        gateraw = (self.GateStates or "").strip()
        if gatedev and "/" not in gatedev:
            return ("GateDevice %r is not a device name (domain/family/member)"
                    % self.GateDevice)
        if gatedev and not gateraw:
            return ("GateDevice is %s but GateStates is empty. GateStates must "
                    "name the state(s) in which the gate is open, e.g. ON"
                    % gatedev)
        if gateraw and not gatedev:
            return ("GateStates is %r but GateDevice is empty. Name the gate "
                    "device, or clear GateStates" % self.GateStates)
        if not gatedev:
            return None
        valid = set(tango.DevState.names)
        names = [s.strip().upper() for s in gateraw.split(",") if s.strip()]
        bad = [s for s in names if s not in valid]
        if bad:
            return ("GateStates names %s, which %s not a Tango state. Valid "
                    "names: %s" % (", ".join(bad),
                                   "is" if len(bad) == 1 else "are",
                                   ", ".join(sorted(valid))))
        self.gatestates = set(names)
        if {"ON", "OFF"} <= self.gatestates or len(self.gatestates) >= 4:
            self.gatewarn = (
                "GateStates = %s looks like it covers every state %s can "
                "publish; the gate would never shut and evaluation would run "
                "just as if no GateDevice were set" % (gateraw, gatedev))
        return None

    def set_status(self, text):
        """Every status line carries any standing gate note. A GateStates
        that never actually gates, or a gate device that cannot be read,
        otherwise shows up only as "the interlock behaves as though it had no
        gate" with nothing on the device to explain why. getattr keeps this
        safe if Tango calls set_status before init_device sets the fields."""
        for note in (getattr(self, "gatefault", ""),
                     getattr(self, "gatewarn", "")):
            if note:
                text = note + "\n" + text
        Device.set_status(self, text)

    def raw_property(self, name):
        """The property as the database holds it, or None if it is not set.

        The value PyTango handed us has already been through a conversion; this
        is what went into it.
        """
        try:
            stored = tango.Database().get_device_property(
                self.get_name(), [name])
        except Exception:
            # Not being able to ask is not evidence of a bad value. The
            # properties were fetched a moment ago, so the database was there.
            return None
        values = stored.get(name) or []
        return values[0] if values else None

    def bool_property_complaint(self, name, value):
        """Say what is wrong with a bool property, or None if nothing is.

        PyTango converts a dtype='bool' device property with

            seq[0].lower() == "true"

        so 'True\\t' -- the word with a tab pasted into Jive behind it -- and
        'False\\t' both arrive as False, identically and without a word said.
        Latching is the one bool here that nothing downstream contradicts: a
        WatchOnly or a Reverse lost this way runs into one of the checks below
        and the server refuses to start, whereas a lost Latching just quietly
        stops latching. leem/safety/interlockP2lens re-granted the P2 permissive
        on every recovery, with Latching reading True in Jive, until someone
        thought to look at the string rather than the property.
        """
        raw = self.raw_property(name)
        if raw is None:
            return None                  # not set; the declared default stands
        meant = raw.strip().lower()
        if meant in ("true", "yes", "y", "t", "on", "1"):
            meant = True
        elif meant in ("false", "no", "n", "f", "off", "0"):
            meant = False
        else:
            return ("%s is %r in the database, which is not a truth value. "
                    "Write it as true or false." % (name, raw))
        if meant != value:
            return ("%s is %r in the database and arrived here as %s. A bool "
                    "property is converted by comparing it with the literal "
                    "\"true\", so anything around the word -- a trailing tab "
                    "pasted into Jive, most often -- reads as False whatever "
                    "it says. Rewrite it as %s, with nothing around it."
                    % (name, raw, value, "true" if meant else "false"))
        return None

    def grants(self, value):
        """Is the input past ThresholdOn, on the safe side?"""
        if self.Reverse:
            return value < self.ThresholdOn
        return value > self.ThresholdOn

    def withdraws(self, value):
        """Is the input back past ThresholdOff, on the unsafe side?"""
        if self.Reverse:
            return value > self.ThresholdOff
        return value < self.ThresholdOff

    def proxy(self, which):
        """Create device proxies lazily, so a database or device that is not up
        yet delays the interlock rather than killing it at start-up."""
        if which == "input":
            if self.inputproxy is None:
                self.inputproxy = tango.DeviceProxy(self.InputDevice)
                self.inputproxy.set_timeout_millis(self.ProxyTimeout)
            return self.inputproxy
        if self.outputproxy is None:
            self.outputproxy = tango.DeviceProxy(self.OutputDevice)
            self.outputproxy.set_timeout_millis(self.ProxyTimeout)
        return self.outputproxy

    def gate_proxy(self):
        if self.gateproxy is None:
            self.gateproxy = tango.DeviceProxy(self.GateDevice)
            self.gateproxy.set_timeout_millis(self.ProxyTimeout)
        return self.gateproxy

    def gate_open(self):
        """True when evaluation should run this cycle. An unreadable gate
        counts as open and says so in Status: for a command-on-trip interlock
        failing towards acting is recoverable and failing towards silence is
        not. Mirrors AlarmNotifier.gate_open."""
        try:
            current = str(self.gate_proxy().state())
        except Exception as exc:
            self.gateproxy = None
            self.gatevalue = "unreadable"
            self.gatefault = ("gate %s unreadable, evaluating anyway: %s"
                              % (self.GateDevice, exc))
            return True
        self.gatefault = ""
        self.gatevalue = current
        return current.upper() in self.gatestates

    def save_bypass(self):
        """Serialise the live bypass for the memorized attribute. Absolute
        epoch times. Call with the lock held."""
        data = {}
        if self.bypassuntil:
            data = {"until": self.bypassuntil, "since": self.bypasssince,
                    "reason": self.bypassreason,
                    "renewals": self.bypassrenewals, "short": self.bypassshort}
        self.pendingbypass = json.dumps(data)
        return self.pendingbypass

    def apply_bypass(self, blob):
        """Restore a bypass from the memorized blob. A stored expiry already
        in the past does NOT re-bypass: bypassrestored is set instead and the
        caller shows it in Status."""
        try:
            data = json.loads(blob) if blob else {}
        except ValueError:
            return
        until = data.get("until", 0.0)
        if not until:
            return
        with self.lock:
            if until > self.now():
                self.bypassuntil = until
                self.bypasssince = data.get("since", until)
                self.bypassreason = data.get("reason", "")
                self.bypassrenewals = int(data.get("renewals", 0))
                self.bypassshort = bool(data.get("short", False))
            else:
                self.bypassrestored = (
                    "a bypass restored from before the restart had already "
                    "expired at %s; came up armed" % self._stamp(until))

    def send(self, cmd):
        if self.WatchOnly:
            return True
        try:
            self.proxy("output").command_inout(cmd)
            return True
        except Exception as exc:
            self.outputproxy = None
            self.set_state(tango.DevState.FAULT)
            self.set_status("Cannot command %s on %s: %s"
                            % (cmd, self.OutputDevice, exc))
            return False

    def trip(self, reason, state=tango.DevState.ALARM):
        """De-assert the permissive and record why. Idempotent."""
        waspermit = self.permit
        wastripped = self.tripped
        self.permit = False
        self.tripped = True
        # Record when a granted permissive is dropped, and also on the first
        # trip of a condition that was never granted in the first place -- the
        # commissioning procedure closes the valve from cold and expects
        # LastTripReason to say so. Not on every repeat, or an outage lasting
        # minutes would keep overwriting the timestamp of its own first cycle.
        if waspermit or not wastripped:
            self.lasttriptime = time.strftime("%Y-%m-%d %H:%M:%S")
            self.lasttripvalue = self.inputvalue
            self.lasttripreason = reason
        self.send(self.OffCommand)
        if self.get_state() != tango.DevState.FAULT or state == tango.DevState.FAULT:
            self.set_state(state)
            self.set_status(reason)

    def grant(self):
        if not self.send(self.OnCommand):
            # send() has already set FAULT and said which command failed. The
            # caller must stop here: falling through to the tail of cycle()
            # would overwrite that with "must rise above", which is both wrong
            # -- the input is past the threshold, that is why we are here --
            # and unfalsifiable, since the FAULT is replaced within the same
            # cycle and never seen. That is how an interlock with no
            # OutputDevice at all spent its life reporting a threshold it had
            # already passed.
            return False
        self.permit = True
        self.tripped = False
        self.cyclessincereassert = 0
        self.set_state(tango.DevState.ON)
        self.set_status("%s granted (%s = %.2f)"
                        % ("Watch" if self.WatchOnly else "Permit",
                           self.InputAttribute, self.inputvalue))
        return True

    def enter_gated(self):
        """Gate shut: do not read, do not command, do not touch LastTrip* or
        the latch. Keepalive alone continues where a granted permissive is
        held up by an output deadman, so closing the gate on the plant does
        not by itself drop the permissive. A command-on-trip interlock sets
        no KeepaliveCommand, so this does nothing there."""
        self.gatewasopen = False
        if self.permit and self.KeepaliveCommand:
            if not self.send(self.KeepaliveCommand):
                return              # send() set FAULT and named the command
        self.set_state(tango.DevState.OFF)
        if self.manuallatch or (self.Latching and self.tripped):
            self.set_status(
                "Gate %s = %s: not evaluating. A latched trip from before the "
                "gate shut is still held; Reset is still required before the "
                "permissive can return" % (self.GateDevice, self.gatevalue))
        elif not self.everread:
            self.set_status("Gate %s = %s: not evaluating (no reading yet)"
                            % (self.GateDevice, self.gatevalue))
        else:
            self.set_status("Gate %s = %s: not evaluating"
                            % (self.GateDevice, self.gatevalue))

    def reopen_gate(self):
        """Gate just opened. Re-arm the failure counters so evaluation starts
        from a clean slate -- as AlarmNotifier.restart does -- and set a
        one-shot so the next lines can trip straight out of the un-granted
        state if the input is already on the unsafe side. permit, tripped and
        the latch are left alone: a condition that is still good is correctly
        carried over, and a real latch must survive until Reset."""
        self.readfailures = 0
        self.beatfailures = 0
        self.stalecount = 0
        self.lastheartbeat = None
        self.cyclessincereassert = 0
        self.cleanslate = True

    def serve_bypass(self):
        """One cycle while bypassed. No trip command, LastTrip* untouched.
        Keepalive still goes out where a deadman needs it, or the bypass
        would cause the very trip it was meant to prevent. The state is the
        whole operator-visible API: DISABLE while there is time to spare,
        STANDBY inside the final BypassWarnMinutes."""
        if self.permit and self.KeepaliveCommand:
            if not self.send(self.KeepaliveCommand):
                return               # send() set FAULT and named the command
        remaining = self.bypassuntil - self.now()
        warn = (not self.bypassshort
                and remaining <= self.BypassWarnMinutes * 60.0)
        self.set_state(tango.DevState.STANDBY if warn
                       else tango.DevState.DISABLE)
        text = ("Bypass expiring: " if warn else "Bypassed: ")
        text += ("%g min left, until %s, reason: %s"
                 % (remaining / 60.0, self._stamp(self.bypassuntil),
                    self.bypassreason))
        if self.bypassrenewals:
            text += (" (%d renewal%s this run, since %s)"
                     % (self.bypassrenewals,
                        "" if self.bypassrenewals == 1 else "s",
                        self._stamp(self.bypasssince)))
        if self.tripped:
            text += (". The output was already commanded off and the latch "
                     "is set; when the bypass ends, Reset then a manual %s "
                     "are needed -- the interlock will not raise it for you"
                     % self.OnCommand)
        self.set_status(text)

    def cycle(self):
        """One poll. Called only from the control thread."""
        # --- bypass ----------------------------------------------------------
        # Outranks the gate and the evaluation. The expiry transition is
        # taken under the lock so a BypassFor arriving in the same instant
        # either renews before it or is refused after it, never straddles.
        with self.lock:
            self.updatecount += 1
            expired = bool(self.bypassuntil) and self.bypassuntil <= self.now()
            if expired:
                self.bypassuntil = 0.0
                self.cleanslate = True      # evaluate fresh, like a gate reopen
                self.save_bypass()
            bypassed = self.bypassuntil > self.now()
        if bypassed:
            self.serve_bypass()
            return

        # --- gate --------------------------------------------------------
        # Cheap early return. With no GateDevice this is a single falsy test
        # and every line below runs exactly as it did before gating existed.
        if self.GateDevice:
            if not self.gate_open():
                self.enter_gated()
                return
            if not self.gatewasopen:
                self.gatewasopen = True
                self.reopen_gate()

        # --- read the input -------------------------------------------------
        try:
            reading = self.proxy("input").read_attribute(self.InputAttribute)
            if reading.quality == tango.AttrQuality.ATTR_INVALID:
                raise ValueError("attribute quality is INVALID")
            value = float(reading.value)
        except Exception as exc:
            self.inputproxy = None
            self.readfailures += 1
            if self.readfailures >= self.MaxReadFailures:
                self.trip("Cannot read %s/%s (%d consecutive failures): %s"
                          % (self.InputDevice, self.InputAttribute,
                             self.readfailures, exc),
                          tango.DevState.FAULT)
            return
        self.readfailures = 0
        self.inputvalue = value
        self.everread = True

        # --- is the publisher still alive? ----------------------------------
        if self.HeartbeatAttribute:
            try:
                beat = self.proxy("input").read_attribute(
                    self.HeartbeatAttribute).value
                self.beatfailures = 0
            except Exception as exc:
                # A heartbeat that is configured but cannot be read is a
                # failure, not an absent heartbeat. Swallowing it would leave
                # this server reporting ON while silently unable to tell a live
                # publisher from a frozen one -- the single thing it exists to
                # detect. Set HeartbeatAttribute to "" to disable it on purpose.
                # Returning here also skips the keepalive below, on purpose:
                # while the state of the publisher is unknown there is no
                # reason to go on reassuring the output device's deadman.
                self.beatfailures += 1
                if self.beatfailures >= self.MaxReadFailures:
                    self.trip("Cannot read heartbeat %s/%s (%d consecutive "
                              "failures): %s. Staleness cannot be detected, so "
                              "the reading of %.2f cannot be trusted"
                              % (self.InputDevice, self.HeartbeatAttribute,
                                 self.beatfailures, exc, value),
                              tango.DevState.FAULT)
                return
            if beat == self.lastheartbeat:
                self.stalecount += 1
            else:
                self.stalecount = 0
                self.lastheartbeat = beat
            if self.stalecount >= self.StaleCycles:
                self.trip("%s/%s frozen for %d cycles; the reading of "
                          "%.2f cannot be trusted"
                          % (self.InputDevice, self.HeartbeatAttribute,
                             self.stalecount, value))
                return

        # --- fresh evaluation after a gate reopen or a bypass ending ----
        # A normal cycle only trips out of the granted state. Just after the
        # gate opens, or a bypass expires or is Armed off, the interlock may
        # be starting from un-granted -- the supply was switched on with the
        # cooling still closed -- and that must trip and command the supply
        # off, not sit in ALARM beside a live supply. A real latch still
        # wins and clears only with Reset.
        if self.cleanslate:
            self.cleanslate = False
            latched = self.manuallatch or (self.Latching and self.tripped)
            if not self.permit and not latched and self.withdraws(value):
                self.trip("re-armed with %s = %.2f already %s ThresholdOff "
                          "(%.2f)" % (self.InputAttribute, value,
                                      "above" if self.Reverse else "below",
                                      self.ThresholdOff))
                return

        # --- threshold with hysteresis --------------------------------------
        latched = self.manuallatch or (self.Latching and self.tripped)
        if self.permit:
            if self.withdraws(value):
                self.trip("%s = %.2f %s ThresholdOff (%.2f)"
                          % (self.InputAttribute, value,
                             "above" if self.Reverse else "below",
                             self.ThresholdOff))
                return
        else:
            if self.grants(value) and not latched:
                if not self.grant():
                    return

        # --- maintain the permissive ----------------------------------------
        if self.permit:
            if self.KeepaliveCommand:
                self.send(self.KeepaliveCommand)
            if self.ReassertCycles > 0:
                self.cyclessincereassert += 1
                if self.cyclessincereassert >= self.ReassertCycles:
                    self.cyclessincereassert = 0
                    self.send(self.OnCommand)
            return

        # Not granted and nothing tripped this cycle: the input is readable but
        # still inside the hysteresis band. Report that explicitly, rather than
        # leaving whatever state an earlier failure set, which would otherwise
        # leave the device stuck in FAULT while reading perfectly well.
        self.set_state(tango.DevState.ALARM)
        if latched:
            self.set_status("No permit: latched off, Reset to clear (%s = %.2f)"
                            % (self.InputAttribute, value))
        else:
            self.set_status("No %s: %s = %.2f, must %s %.2f"
                            % ("watch" if self.WatchOnly else "permit",
                               self.InputAttribute, value,
                               "fall below" if self.Reverse else "rise above",
                               self.ThresholdOn))
    # PROTECTED REGION END #    //  AnalogInterlock.protected_methods

    def always_executed_hook(self):
        # PROTECTED REGION ID(AnalogInterlock.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  AnalogInterlock.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(AnalogInterlock.delete_device) ENABLED START #
        with self.lock:
            self.save_bypass()
        self.stop_event.set()
        if self.ctrlloop is not None and self.ctrlloop.is_alive():
            self.ctrlloop.join(timeout=2.0 + self.PollPeriod)
        # Stopping deliberately does NOT de-assert the permissive: an Init from
        # Jive would otherwise trip a running experiment. Keepalives stop, so
        # the output device's deadman takes over if this server does not come
        # back.
        self.permit = False
        # PROTECTED REGION END #    //  AnalogInterlock.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_InputValue(self):
        # PROTECTED REGION ID(AnalogInterlock.InputValue_read) ENABLED START #
        if self.readfailures > 0:
            return (self.inputvalue, time.time(),
                    tango.AttrQuality.ATTR_INVALID)
        return self.inputvalue
        # PROTECTED REGION END #    //  AnalogInterlock.InputValue_read

    def read_Permit(self):
        # PROTECTED REGION ID(AnalogInterlock.Permit_read) ENABLED START #
        return self.permit
        # PROTECTED REGION END #    //  AnalogInterlock.Permit_read

    def read_Tripped(self):
        # PROTECTED REGION ID(AnalogInterlock.Tripped_read) ENABLED START #
        return self.tripped
        # PROTECTED REGION END #    //  AnalogInterlock.Tripped_read

    def read_LastTripTime(self):
        # PROTECTED REGION ID(AnalogInterlock.LastTripTime_read) ENABLED START #
        return self.lasttriptime
        # PROTECTED REGION END #    //  AnalogInterlock.LastTripTime_read

    def read_LastTripValue(self):
        # PROTECTED REGION ID(AnalogInterlock.LastTripValue_read) ENABLED START #
        return self.lasttripvalue
        # PROTECTED REGION END #    //  AnalogInterlock.LastTripValue_read

    def read_LastTripReason(self):
        # PROTECTED REGION ID(AnalogInterlock.LastTripReason_read) ENABLED START #
        return self.lasttripreason
        # PROTECTED REGION END #    //  AnalogInterlock.LastTripReason_read

    def read_ThresholdOnRB(self):
        # PROTECTED REGION ID(AnalogInterlock.ThresholdOnRB_read) ENABLED START #
        return self.ThresholdOn
        # PROTECTED REGION END #    //  AnalogInterlock.ThresholdOnRB_read

    def read_ThresholdOffRB(self):
        # PROTECTED REGION ID(AnalogInterlock.ThresholdOffRB_read) ENABLED START #
        return self.ThresholdOff
        # PROTECTED REGION END #    //  AnalogInterlock.ThresholdOffRB_read

    def read_LatchingRB(self):
        # PROTECTED REGION ID(AnalogInterlock.LatchingRB_read) ENABLED START #
        # The value in force, not the string in the database: the point of
        # showing it is that the two can differ.
        return self.Latching
        # PROTECTED REGION END #    //  AnalogInterlock.LatchingRB_read

    def read_UpdateCount(self):
        return self.updatecount

    def read_Bypassed(self):
        return self.bypassuntil > self.now()

    def read_BypassRemaining(self):
        rem = self.bypassuntil - self.now()
        return rem / 60.0 if rem > 0 else 0.0

    def read_BypassUntil(self):
        return self._stamp(self.bypassuntil)

    def read_BypassSince(self):
        return self._stamp(self.bypasssince if self.bypassuntil else 0.0)

    def read_BypassReason(self):
        return self.bypassreason if self.bypassuntil else ""

    def read_BypassRenewals(self):
        return self.bypassrenewals if self.bypassuntil else 0

    def read_BypassState(self):
        with self.lock:
            return self.save_bypass()

    def write_BypassState(self, value):
        # Tango replays the memorized value at start-up, possibly before
        # init_device has built the fields. Keep the blob either way and
        # apply what can be applied now.
        self.pendingbypass = value
        if getattr(self, "lock", None) is not None:
            self.apply_bypass(value)

    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def Reset(self):
        # PROTECTED REGION ID(AnalogInterlock.Reset) ENABLED START #
        # Only meaningful with Latching = True. Clears the software latch; it
        # has no effect on any hardware latch, which still needs its button.
        self.tripped = False
        self.manuallatch = False
        self.readfailures = 0
        self.beatfailures = 0
        self.stalecount = 0
        self.lastheartbeat = None
        self.set_state(tango.DevState.INIT)
        self.set_status("Latch cleared, waiting for next reading")
        # PROTECTED REGION END #    //  AnalogInterlock.Reset

    @command(
    )
    @DebugIt()
    def Trip(self):
        # PROTECTED REGION ID(AnalogInterlock.Trip) ENABLED START #
        # Manual de-assert, e.g. to test the chain without touching the water.
        # This latches whatever the Latching property says: a person asked for
        # the permissive to drop, so it stays down until a person clears it with
        # Reset. Without this the next cycle would re-grant it a second later
        # and the test would look like it had not worked.
        self.manuallatch = True
        self.trip("Tripped manually; Reset to clear")
        # PROTECTED REGION END #    //  AnalogInterlock.Trip

    def do_bypass(self, argin):
        """Shared body of BypassFor, so parsing and the cap live in one
        place. Renewal is BypassFor again on an already-bypassed device;
        it is absolute -- 'BypassFor 4 ...' means four hours from now,
        whatever was left -- so two distracted calls cannot compound."""
        if self.WatchOnly:
            raise ValueError(
                "this is a watch-only device: it commands nothing, so there "
                "is nothing to bypass. What silences it is SnoozeFor on the "
                "AlarmNotifier rule that watches it")
        parts = (argin or "").split(None, 1)
        if len(parts) < 2 or not parts[1].strip():
            raise ValueError(
                "expected 'hours reason', e.g. '8 evaporador sin "
                "refrigeracion'. The reason is mandatory: it goes into the "
                "record and into the mail")
        try:
            hours = float(parts[0])
        except ValueError:
            raise ValueError("%r is not a number of hours" % parts[0])
        if hours <= 0:
            raise ValueError("hours must be positive; use Arm to end a bypass")
        if hours > self.MaxBypassHours:
            raise ValueError(
                "at most %g h in one request (MaxBypassHours). Renew with "
                "BypassFor again for another %g h from then; each renewal "
                "needs its own reason and leaves its own record"
                % (self.MaxBypassHours, self.MaxBypassHours))
        reason = parts[1].strip()
        now = self.now()
        with self.lock:
            renewal = self.bypassuntil > now
            self.bypassuntil = now + hours * 3600.0
            self.bypassreason = reason
            self.bypassshort = hours * 3600.0 < self.BypassWarnMinutes * 60.0
            self.bypassrestored = ""
            if renewal:
                self.bypassrenewals += 1
            else:
                self.bypasssince = now
                self.bypassrenewals = 0
            posttrip = self.tripped
            self.save_bypass()
        msg = ("bypassed for %g h%s, reason: %s"
               % (hours,
                  " (renewal #%d)" % self.bypassrenewals if renewal else "",
                  reason))
        if posttrip:
            msg += (". NOTE: the output is already off and the latch set; "
                    "the bypass holds off the interlock but does not raise "
                    "the output -- Reset then a manual %s once it ends"
                    % self.OnCommand)
        return msg

    @command(dtype_in='str', dtype_out='str',
             doc_in="hours and a mandatory reason, e.g. "
                    "'8 evaporador sin refrigeracion'",
             doc_out="what was done")
    @DebugIt()
    def BypassFor(self, argin):
        # PROTECTED REGION ID(AnalogInterlock.BypassFor) ENABLED START #
        # Scalar DevString: ATKPanel -- the only interface most of the lab
        # opens -- will not offer a DevVarStringArray command. Same reason
        # AlarmNotifier grew SnoozeFor alongside Snooze.
        return self.do_bypass(argin)
        # PROTECTED REGION END #    //  AnalogInterlock.BypassFor

    def do_arm(self):
        """Body of Arm, kept out of the command wrapper so it is callable
        without a logger. Ends the bypass now and forces a fresh evaluation
        before the next action decision, exactly as a gate reopening does."""
        now = self.now()
        with self.lock:
            was = self.bypassuntil > now
            self.bypassuntil = 0.0
            self.cleanslate = True
            self.save_bypass()
        return "armed" if was else "was not bypassed; armed anyway"

    @command(dtype_out='str')
    @DebugIt()
    def Arm(self):
        # PROTECTED REGION ID(AnalogInterlock.Arm) ENABLED START #
        return self.do_arm()
        # PROTECTED REGION END #    //  AnalogInterlock.Arm

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(AnalogInterlock.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((AnalogInterlock,), args=args, **kwargs)
    # PROTECTED REGION END #    //  AnalogInterlock.main


if __name__ == '__main__':
    main()
