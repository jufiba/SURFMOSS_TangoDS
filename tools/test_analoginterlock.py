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
        HeartbeatAttribute = ""
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

        def __init__(self, **kw):
            self.value = 0.0
            self.sent = []
            self.output_up = True
            self.state = tango.DevState.INIT
            self.status = ""
            for key, val in kw.items():
                setattr(self, key, val)
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
            self.inputproxy = None
            self.outputproxy = None

        def set_state(self, state):
            self.state = state

        def get_state(self):
            return self.state

        def set_status(self, status):
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
          "No permit: flow = 5.00, must rise above 9.00")
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
          "flow = 7.00 below ThresholdOff (8.00)")
    check("Off sent", dev.sent[-1], "Off")

    print("\nreverse: the input must stay low")
    dev = Fake(Reverse=True, InputAttribute="temperature",
               ThresholdOn=30.0, ThresholdOff=35.0)
    dev.value = 40.0
    dev.cycle()
    check("above ThresholdOn -> no permit", dev.permit, False)
    check("status", dev.status,
          "No permit: temperature = 40.00, must fall below 30.00")
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
          "temperature = 36.00 above ThresholdOff (35.00)")

    print("\nwatch only: the same decisions, no commands at all")
    dev = Fake(WatchOnly=True, OutputDevice="")
    dev.value = 10.0
    dev.cycle()
    check("granted", dev.permit, True)
    check("state", dev.state, tango.DevState.ON)
    check("status says watch", dev.status, "Watch granted (flow = 10.00)")
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
          dev.status.startswith("Cannot command On on"), True)
    check("and does not lie about the threshold",
          "must rise above" in dev.status, False)


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
    refusals(repo)

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
