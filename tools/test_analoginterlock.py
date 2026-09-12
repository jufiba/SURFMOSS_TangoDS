#!/usr/bin/env python3
"""Regression tests for AnalogInterlock's decisions and its refusals to start.

Neither audit in tools/ can see the defect these were written for: a server
that diagnoses a failure correctly and then overwrites the diagnosis with a
later line. `mossbauer/warn/watercompressor` spent weeks reporting

    ALARM | No permit: newcompressor = 10.80, must rise above 9.00

with the flow at 10.8 against a threshold of 9, because grant() failed to
command an OutputDevice it did not have, set FAULT saying so, and the tail of
cycle() overwrote it in the same cycle. See docs/DS-architecture.md section 3.

Two halves:

  the decisions   cycle() driven directly against a stub, so all four
                  combinations of Reverse x WatchOnly run in a second and the
                  refused command can be produced on demand
  the refusals    a real server started from a -file= database, because the
                  properties have to be fetched by PyTango and the refusal has
                  to leave the server answering rather than killing the process

Neither half touches a live interlock. Needs PyTango, so it runs on a Pi or on
wolframite, not on a laptop.

Usage:  python3 tools/test_analoginterlock.py [--root PATH]
Exit:   0 all passed, 1 failures, 2 could not run.
"""

import os
import subprocess
import sys
import threading
import time

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import tango
except ImportError:
    print("PyTango is not importable here; run this on a Pi or on wolframite")
    sys.exit(2)


FAILS = 0


def check(what, got, want):
    global FAILS
    if got != want:
        FAILS += 1
        print("  FAIL %-42s got %r want %r" % (what, got, want))
    else:
        print("  ok   %-42s %r" % (what, got))


def build_fake(cls):
    """A subclass of the real server with the Device machinery stubbed out.

    The properties are declared as plain class attributes so that they can be
    set per test; everything cycle() calls on Device -- set_state, get_state,
    set_status, proxy -- is answered here. cycle(), grant(), trip(), send()
    and the two comparisons are the real ones.
    """

    class Fake(cls):
        InputDevice = "stub/in/1"
        InputAttribute = "flow"
        HeartbeatAttribute = "UpdateCount"   # decision tests want it on and
        #                                      quiet; sentinel() overrides it
        OutputDevice = "stub/out/1"
        OnCommand = "On"
        OffCommand = "Off"
        KeepaliveCommand = "Keepalive"
        WatchOnly = False
        Reverse = False
        ThresholdOn = 9.0
        ThresholdOff = 8.0
        PollPeriod = 1.0
        MaxReadFailures = 3
        StaleCycles = 5
        Latching = False
        ReassertCycles = 0
        ProxyTimeout = 800
        GateDevice = ""
        GateStates = ""
        MaxBypassHours = 8.0
        BypassWarnMinutes = 30.0

        def __init__(self, **kw):
            self.value = 0.0
            self.sent = []
            self.output_up = True
            self.state = tango.DevState.INIT
            self.status = ""
            for key, val in kw.items():
                setattr(self, key, val)
            self.clean_properties()          # sets self.prop and self.propnotes
            self.inputvalue = float("nan")
            self.permit = False
            self.tripped = False
            self.lasttriptime = "never"
            self.lasttripvalue = float("nan")
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
            self.gatestates = set()
            self.gatewasopen = False
            self.cleanslate = False
            self.gatevalue = ""
            self.gatewarn = ""
            self.gatefault = ""
            self.heartbeatoff = ""
            self.everread = False
            self.lock = threading.Lock()
            self.bypassuntil = 0.0
            self.bypasssince = 0.0
            self.bypassreason = ""
            self.bypassrenewals = 0
            self.bypassshort = False
            self.bypassrestored = ""
            self.pendingbypass = ""

        def set_state(self, state):
            self.state = state

        def get_state(self):
            return self.state

        def set_status(self, status):
            # Mirror the real set_status: the standing notes are prepended so
            # a test can see an altered property or a dead gate in Status.
            # With clean config every note is empty and status is unchanged.
            for note in (getattr(self, "gatefault", ""),
                         getattr(self, "gatewarn", ""),
                         getattr(self, "heartbeatoff", "")):
                if note:
                    status = note + "\n" + status
            for note in getattr(self, "propnotes", {}).values():
                if note:
                    status = note + "\n" + status
            self.status = status

        def proxy(self, which):
            return self

        def read_attribute(self, name):
            reading = type("R", (), {})()
            reading.value = self.value
            reading.quality = tango.AttrQuality.ATTR_VALID
            return reading

        def command_inout(self, cmd):
            if not self.output_up:
                raise tango.DevFailed("the stub output is not there")
            self.sent.append(cmd)

    return Fake


def decisions(cls):
    Fake = build_fake(cls)

    print("\nnormal: the input must stay high")
    dev = Fake()
    dev.value = 5.0
    dev.cycle()
    check("below ThresholdOn -> no permit", dev.permit, False)
    check("state", dev.state, tango.DevState.ALARM)
    check("status", dev.status,
          "No permit: 'flow' = 5.00, must rise above 9.00")
    dev.value = 10.0
    dev.cycle()
    check("above ThresholdOn -> permit", dev.permit, True)
    check("state", dev.state, tango.DevState.ON)
    check("On then Keepalive sent", dev.sent, ["On", "Keepalive"])
    dev.value = 8.5
    dev.cycle()
    check("inside the hysteresis -> still granted", dev.permit, True)
    dev.value = 7.0
    dev.cycle()
    check("below ThresholdOff -> tripped", (dev.permit, dev.tripped),
          (False, True))
    check("reason", dev.lasttripreason,
          "'flow' = 7.00 below ThresholdOff (8.00)")
    check("Off sent", dev.sent[-1], "Off")

    print("\nreverse: the input must stay low")
    dev = Fake(Reverse=True, InputAttribute="temperature",
               ThresholdOn=30.0, ThresholdOff=35.0)
    dev.value = 40.0
    dev.cycle()
    check("above ThresholdOn -> no permit", dev.permit, False)
    check("status", dev.status,
          "No permit: 'temperature' = 40.00, must fall below 30.00")
    dev.value = 25.0
    dev.cycle()
    check("below ThresholdOn -> permit", dev.permit, True)
    dev.value = 32.0
    dev.cycle()
    check("inside the hysteresis -> still granted", dev.permit, True)
    dev.value = 36.0
    dev.cycle()
    check("above ThresholdOff -> tripped", (dev.permit, dev.tripped),
          (False, True))
    check("reason", dev.lasttripreason,
          "'temperature' = 36.00 above ThresholdOff (35.00)")

    print("\nwatch only: the same decisions, no commands at all")
    dev = Fake(WatchOnly=True, OutputDevice="")
    dev.value = 10.0
    dev.cycle()
    check("granted", dev.permit, True)
    check("state", dev.state, tango.DevState.ON)
    check("status says watch", dev.status, "Watch granted ('flow' = 10.00)")
    check("nothing commanded", dev.sent, [])
    dev.value = 7.0
    dev.cycle()
    check("trips all the same", dev.tripped, True)
    check("still nothing commanded", dev.sent, [])

    print("\nthe output refuses On -- the reported bug")
    dev = Fake()
    dev.output_up = False
    dev.value = 10.0
    dev.cycle()
    check("not granted", dev.permit, False)
    check("state is FAULT", dev.state, tango.DevState.FAULT)
    check("the status names the command",
          dev.status.startswith("Cannot command 'On' on"), True)
    check("and does not lie about the threshold",
          "must rise above" in dev.status, False)


def sentinel(cls):
    """HeartbeatAttribute's off switch, and the quote / whitespace repair
    clean_properties does to every str property. Written for the third
    property-parsing incident: '' pasted into Jive to disable the heartbeat,
    stored as the two-character "", which is truthy and disabled nothing.
    """
    Fake = build_fake(cls)

    print("\nheartbeat off switch: 'none', '-', empty, whitespace")
    for spelling in ("none", "None", "NONE", " none ", "-", " - "):
        d = Fake(HeartbeatAttribute=spelling)
        check("%-8r disables staleness" % spelling, d.heartbeat_name(), "")
    check("'' disables (unit level)",
          Fake(HeartbeatAttribute="").heartbeat_name(), "")
    check("whitespace-only disables",
          Fake(HeartbeatAttribute="   ").heartbeat_name(), "")
    check("plain 'none' is not flagged as altered",
          "HeartbeatAttribute" in Fake(HeartbeatAttribute="none").propnotes,
          False)

    print("\nliteral quotes detected, unwrapped, and shown in Status")
    d = Fake(HeartbeatAttribute='""')
    check("'\"\"' -> disabled", d.heartbeat_name(), "")
    check("'\"\"' -> altered-value note recorded",
          "HeartbeatAttribute" in d.propnotes, True)
    d.set_status("body")
    check("'\"\"' -> note reaches Status every line",
          d.status.startswith("HeartbeatAttribute was") and
          d.status.endswith("\nbody"), True)
    check("\"''\" -> disabled",
          Fake(HeartbeatAttribute="''").heartbeat_name(), "")
    d = Fake(HeartbeatAttribute='"UpdateCount"')
    check("'\"UpdateCount\"' -> UpdateCount", d.heartbeat_name(), "UpdateCount")
    check("  and the unwrap is noted", "HeartbeatAttribute" in d.propnotes, True)
    d = Fake(HeartbeatAttribute="  UpdateCount  ")
    check("padded -> stripped and used", d.heartbeat_name(), "UpdateCount")
    check("  a plain strip is not noted",
          "HeartbeatAttribute" in d.propnotes, False)

    print("\nheartbeat off -> Status says so, on every cycle not just the first")
    d = Fake(HeartbeatAttribute="none", WatchOnly=True, OutputDevice="")
    d.value = 12.0
    d.cycle()
    first = d.status
    d.cycle()
    check("cycle 1 Status carries the OFF note",
          first.startswith("staleness detection is OFF"), True)
    check("cycle 2 Status still carries it",
          d.status.startswith("staleness detection is OFF"), True)
    check("the note names the input device", "'stub/in/1'" in d.status, True)
    on = Fake(HeartbeatAttribute="UpdateCount", WatchOnly=True, OutputDevice="")
    on.value = 12.0
    on.cycle()
    check("a named heartbeat leaves no OFF note", on.heartbeatoff, "")

    print("\na configured but unreadable heartbeat still trips FAULT")

    class NoBeat(Fake):
        def read_attribute(self, name):
            if name == "UpdateCount":
                raise tango.DevFailed("no such attribute")
            r = type("R", (), {})()
            r.value, r.quality = self.value, tango.AttrQuality.ATTR_VALID
            return r

    d = NoBeat(HeartbeatAttribute="UpdateCount", MaxReadFailures=3)
    d.value = 12.0
    for _ in range(3):
        d.cycle()
    check("state", d.state, tango.DevState.FAULT)
    check("reason names the heartbeat, in repr",
          "heartbeat" in d.lasttripreason and
          "'UpdateCount'" in d.lasttripreason, True)


class _GateStub:
    """Just enough of a DeviceProxy for gate_open(): a .state() to read."""

    def __init__(self):
        self.st = tango.DevState.OFF

    def state(self):
        return self.st


def gate(cls):
    """GateDevice / GateStates. The gate itself is rechecked every cycle --
    gate_open() reads the stub fresh each time -- but until 11-Sep-2026
    nothing put State/Status back once the gate reopened, or a bypass ended,
    while a permit granted before the closure was carried straight through
    underneath: cycle()'s 'maintain the permissive' tail only sent Keepalive
    and returned, since neither grant() nor trip() had anything to do. Found
    on leem/warn/turbotemp and leem/safety/interlockhv1, both of which can
    sit safely granted across a gate cycle. See docs/DS-architecture.md
    section 3.
    """
    Base = build_fake(cls)

    class Gated(Base):
        GateDevice = "stub/gate/1"
        GateStates = "ON"

        def __init__(self, **kw):
            super().__init__(**kw)
            self.gate = _GateStub()
            err = self.gate_config()      # populate self.gatestates, as
            assert err is None, err       # init_device does

        def gate_proxy(self):
            return self.gate

    print("\ngate: reopening while a permit is carried through must not get "
          "stuck")
    dev = Gated()
    dev.value = 10.0                      # stays on the safe side throughout
    dev.gate.st = tango.DevState.ON
    dev.cycle()
    check("gate open -> granted", (dev.state, dev.permit),
          (tango.DevState.ON, True))
    dev.gate.st = tango.DevState.OFF
    dev.cycle()
    check("gate shuts -> OFF, not evaluating, permit held underneath",
          (dev.state, dev.permit), (tango.DevState.OFF, True))
    check("status says not evaluating",
          "not evaluating" in dev.status, True)
    dev.gate.st = tango.DevState.ON
    dev.cycle()
    check("gate reopens, still safe -> ON restored, not stuck at OFF",
          (dev.state, dev.permit), (tango.DevState.ON, True))
    check("status says granted again",
          dev.status, "Permit granted ('flow' = 10.00)")

    print("\nbypass ending while a permit is carried through: same fix")
    dev2 = Base()
    dev2.value = 10.0
    dev2.cycle()
    dev2.bypassuntil = dev2.now() + 3600.0
    dev2.bypasssince = dev2.now()
    dev2.cycle()
    check("bypassed -> DISABLE, permit held underneath",
          (dev2.state, dev2.permit), (tango.DevState.DISABLE, True))
    dev2.bypassuntil = dev2.now() - 1.0   # force expiry
    dev2.cycle()
    check("bypass ends, still safe -> ON restored, not stuck at DISABLE",
          (dev2.state, dev2.permit), (tango.DevState.ON, True))


PORT = 10123
NAME = "mossbauer/test/interlock"

REFUSALS = [
    ("no output and no WatchOnly",
     {}, "no OutputDevice, and WatchOnly is not set"),
    ("WatchOnly together with an OutputDevice",
     {"WatchOnly": "true", "OutputDevice": "stub/out/1"},
     "Watching and commanding are different jobs"),
    ("Reverse with the thresholds the normal way round",
     {"WatchOnly": "true", "Reverse": "true"},
     "ThresholdOff (8) must be above ThresholdOn (9)"),
    ("watch-only, properly configured",
     {"WatchOnly": "true"}, None),
]


def refusals(repo):
    global FAILS
    dbfile = "/tmp/analoginterlock-test.db"
    url = "tango://localhost:%d/%s#dbase=no" % (PORT, NAME)
    code = ("import sys; sys.path.insert(0, %r);"
            "from AnalogInterlock.AnalogInterlock import main;"
            "sys.argv = ['AnalogInterlock', 'test', '-file=%s',"
            "'-ORBendPoint', 'giop:tcp::%d']; main()"
            % (os.path.join(repo, "AnalogInterlock"), dbfile, PORT))

    for title, extra, want in REFUSALS:
        props = {"InputDevice": "stub/in/1", "InputAttribute": "flow",
                 "ThresholdOn": "9", "ThresholdOff": "8"}
        props.update(extra)
        with open(dbfile, "w") as handle:
            handle.write('AnalogInterlock/test/DEVICE/AnalogInterlock: "%s"\n'
                         % NAME)
            for key, val in props.items():
                handle.write('%s->%s: "%s"\n' % (NAME, key, val))
        proc = subprocess.Popen([sys.executable, "-c", code],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)
        state = status = None
        for _ in range(40):
            time.sleep(0.25)
            try:
                dev = tango.DeviceProxy(url)
                state, status = dev.state(), dev.status()
                break
            except Exception:
                if proc.poll() is not None:
                    break
        print("\n%s" % title)
        if state is None:
            print("  FAIL the server never answered; it exited %s\n%s"
                  % (proc.poll(), proc.stderr.read().decode()[-300:]))
            FAILS += 1
        elif want is None:
            ok = state != tango.DevState.FAULT or "OutputDevice" not in status
            print("  %s starts: %s | %s"
                  % ("ok  " if ok else "FAIL", state, status))
            FAILS += 0 if ok else 1
        else:
            ok = state == tango.DevState.FAULT and want in status
            print("  %s %s | %s" % ("ok  " if ok else "FAIL", state, status))
            FAILS += 0 if ok else 1
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    os.path.exists(dbfile) and os.unlink(dbfile)


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]

    sys.path.insert(0, os.path.join(repo, "AnalogInterlock"))
    from AnalogInterlock.AnalogInterlock import AnalogInterlock

    decisions(AnalogInterlock)
    sentinel(AnalogInterlock)
    gate(AnalogInterlock)
    refusals(repo)

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
