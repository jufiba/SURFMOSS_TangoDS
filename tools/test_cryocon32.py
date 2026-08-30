#!/usr/bin/env python3
"""Regression tests for CryoCon32: a channel that is not reading, and start-up.

Written on 30-Aug-2026, when mossbauer/temperature/criostat could not read
TemperatureA. The controller was answering

    INPUT? A   ->   '-------'

which the manual defines as the Sensor Fault Display: seven dashes mean the
sensor is open, disconnected or shorted (seven dots would mean a reading
outside the calibration curve). An honest "no reading", and float() on it
raised ValueError all the way to the client, so an unplugged sensor looked
like a broken server.

Four faults were fixed and each has a test here:

    the dashes reach the client as INVALID with the reason in the status
    init_device no longer writes LOOP 1:TYPE PID, which used to put the
        control loop back into PID on every restart, Init included
    read_HeaterLevel ended in a bare `else: return 2`, so any answer it did
        not recognise -- an empty one included -- was reported as HIGH
    delete_device closed a port that might never have opened

Everything runs against a stub serial port. No controller is contacted.

Usage:  python3 tools/test_cryocon32.py [--root PATH]
Exit:   0 all passed, 1 failures, 2 could not run.
"""

import os
import sys

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAILS = 0


def check(what, got, want):
    global FAILS
    if got != want:
        FAILS += 1
        print("  FAIL %-46s got %r want %r" % (what, got, want))
    else:
        print("  ok   %-46s %r" % (what, got))


REPLIES = {
    "*IDN?": "Cryocon Model 32, Rev 6.20H\n",
    "CONTROL?": "ON \n",
    "INPUT? A": "-------\n",
    "INPUT? B": "312.953064\n",
    "LOOP 1:SETPT?": "20.000000K\n",
    "LOOP 1:RANGE?": "HI \n",
}


class Port:
    """Enough of serial.Serial to drive the server, recording every write."""

    def __init__(self, replies=None, fail=False):
        self.replies = dict(REPLIES if replies is None else replies)
        self.written = []
        self.pending = ""
        self.closed = False
        self.fail = fail

    def reset_input_buffer(self):
        pass

    def write(self, data):
        if self.fail:
            raise OSError("the adapter has gone")
        self.written.append(data.decode("ascii").strip())
        self.pending = self.replies.get(self.written[-1], "")

    def readline(self):
        reply, self.pending = self.pending, ""
        return reply.encode("ascii")

    def close(self):
        self.closed = True


def build(module, tango, port, refuse=False):
    """The server with Device stubbed out and serial replaced by our port."""

    class FakeSerialModule:
        SerialException = module.serial.SerialException

        @staticmethod
        def Serial(*args, **kwargs):
            if refuse:
                raise FakeSerialModule.SerialException(
                    "could not open port: [Errno 2] No such file or directory")
            return port

    class Fake(module.CryoCon32):
        SerialPort = "/dev/stub"
        SerialSpeed = 9600

        def __init__(self):
            self.state = tango.DevState.UNKNOWN
            self.statustext = ""

        def set_state(self, state):
            self.state = state

        def get_state(self):
            return self.state

        def set_status(self, text):
            self.statustext = text

        def error_stream(self, *a):
            pass

        def debug_stream(self, *a):
            pass

    module.serial = FakeSerialModule
    dev = Fake()
    dev.ser = None
    dev.problems = {}
    dev.lastreply = ""
    dev.lastconnect = 0.0
    dev.lastcontrol = 0.0
    return dev


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]

    sys.path.insert(0, os.path.join(repo, "CryoCon32"))
    try:
        import tango
        import importlib
        importlib.import_module("CryoCon32.CryoCon32")
        module = sys.modules["CryoCon32.CryoCon32"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2
    real_serial = module.serial

    print("\nstart-up writes only the display units")
    port = Port()
    dev = build(module, tango, port)
    dev._connect()
    check("state follows CONTROL?", dev.state, tango.DevState.ON)
    check("no LOOP 1:TYPE was sent",
          [w for w in port.written if w.startswith("LOOP 1:TYPE")], [])
    check("both channels asked for K",
          [w for w in port.written if "UNITS" in w],
          ["INPUT A:UNITS K", "INPUT B:UNITS K"])

    print("\na channel with a sensor fault: seven dashes")
    value = dev.read_TemperatureA()
    check("quality", value[2], tango.AttrQuality.ATTR_INVALID)
    check("status names the channel", "Channel A is not reading" in
          dev.statustext, True)
    check("and quotes what the controller said", "'-------'" in
          dev.statustext, True)

    print("\na reading outside the calibration curve: seven dots")
    port.replies["INPUT? A"] = ".......\n"
    check("quality", dev.read_TemperatureA()[2],
          tango.AttrQuality.ATTR_INVALID)

    print("\nthe healthy channel is unaffected, and the status says so")
    check("TemperatureB", dev.read_TemperatureB(), 312.953064)
    check("status still reports A", "Channel A is not reading" in
          dev.statustext, True)
    port.replies["INPUT? A"] = "19.876\n"
    check("A recovers", dev.read_TemperatureA(), 19.876)
    check("status back to normal", dev.statustext,
          "Connected to CryoCon32 on /dev/stub")

    print("\nthe setpoint comes back with its unit attached")
    check("SetPoint", dev.read_SetPoint(), 20.0)
    port.replies["LOOP 1:SETPT?"] = "20.000000C\n"
    check("and in C it is still a number", dev.read_SetPoint(), 20.0)

    print("\nthe heater range")
    for reply, want in (("LOW\n", 0), ("MID\n", 1), ("HI \n", 2),
                        ("HIGH\n", 2)):
        port.replies["LOOP 1:RANGE?"] = reply
        check("%-6r -> %s" % (reply, want), dev.read_HeaterLevel(), want)
    for reply in ("\n", "WHAT\n"):
        port.replies["LOOP 1:RANGE?"] = reply
        got = dev.read_HeaterLevel()
        check("%-7r is INVALID, not HIGH" % reply,
              got[2] if isinstance(got, tuple) else got,
              tango.AttrQuality.ATTR_INVALID)

    print("\nthe control loop being switched off at the front panel")
    port.replies["CONTROL?"] = "OFF\n"
    dev.lastcontrol = 0.0
    dev.always_executed_hook()
    check("state", dev.state, tango.DevState.OFF)

    print("\nthe controller is not there when the server starts")
    dev = build(module, tango, Port(), refuse=True)
    dev._connect()
    check("state", dev.state, tango.DevState.FAULT)
    check("status says why", "could not open port" in dev.statustext, True)
    check("delete_device does not mind", dev.delete_device(), None)

    print("\nand is picked up when it appears, with no Init")
    port = Port()
    dev = build(module, tango, port)
    dev.state = tango.DevState.FAULT
    dev.lastconnect = 0.0
    dev.always_executed_hook()
    check("state", dev.state, tango.DevState.ON)

    print("\nsomething answering that is not a CryoCon32")
    port = Port({"*IDN?": "Lakeshore 335\n"})
    dev = build(module, tango, port)
    dev._connect()
    check("state", dev.state, tango.DevState.FAULT)
    check("status quotes it", "Lakeshore 335" in dev.statustext, True)

    module.serial = real_serial
    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
