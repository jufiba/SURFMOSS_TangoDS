#!/usr/bin/env python3
"""Regression tests for FUGMCP's serial framing.

On 15-sep-2026 leem/power/hv2 sat in FAULT reporting

    Error writing SetVoltage from FUG MCP 429774>S0 984.429774

while the supply itself was perfectly healthy and holding 619 V on the LEEM's
microchannel plate. That string is the tail of an earlier reply glued to the
echo of the command just sent: one read had hit its 0.5 s timeout, left its
bytes in the port, and from then on every exchange read the previous answer.

The failure mattered beyond the wrong string. leem/safety/interlockhv2 gates
on hv2 being ON, so a supply that is energised but reports FAULT falls outside
its own water interlock -- protection switched itself off exactly when the
equipment was misbehaving.

What is checked here: that the port is drained before every write, that a
reply is matched against the command that asked for it, that the echo the
supply sometimes emits is skipped, that silence raises instead of returning an
empty line that later parses into nonsense, and that a genuine refusal from the
supply ('E1') still reaches the caller unchanged.

Everything runs against a stub serial port. No supply is contacted.

Usage:  python3 tools/test_fugmcp.py [--root PATH]
Exit:   0 all passed, 1 failures, 2 could not run.
"""

import os
import sys
import threading
import types

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAILS = 0


def check(what, got, want):
    global FAILS
    if got != want:
        FAILS += 1
        print("  FAIL %-52s got %r want %r" % (what, got, want))
    else:
        print("  ok   %-52s %r" % (what, got))


class StubSerial:
    """Enough of serial.Serial to drive _txn.

    `stale` is what is already sitting in the port before anyone writes --
    the leftovers of a timed-out exchange. `script` is a list of replies, one
    per write, each reply a list of lines the supply sends back. A reply of []
    is a supply that stays silent, which is how a read timeout looks.
    """

    def __init__(self, script=None, stale=()):
        self.script = [list(r) for r in (script or [])]
        self.buffer = list(stale)
        self.written = []
        self.drains = 0

    def reset_input_buffer(self):
        self.drains += 1
        self.buffer = []

    def write(self, data):
        self.written.append(data)
        if self.script:
            self.buffer.extend(self.script.pop(0))

    def readline(self):
        if self.buffer:
            return self.buffer.pop(0)
        return b""

    def close(self):
        pass


def build(module, sock=None):
    """The server with Device stubbed out and the serial port replaced."""

    class Fake(module.FUGMCP):
        SerialPort = "/dev/stub"
        Speed = 625000
        DeadmanTimeout = 0.0

        def __init__(self):
            self.state = None
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

    dev = Fake()
    dev.ser = sock if sock is not None else StubSerial()
    dev._io_lock = threading.Lock()
    return dev


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]

    # A stub serial before the import, so this runs where pyserial is not
    # installed as well as on the Pi where it is.
    sys.modules.setdefault("serial", types.ModuleType("serial"))
    sys.modules["serial"].SerialException = type(
        "SerialException", (Exception,), {})
    sys.modules["serial"].Serial = object
    sys.modules["serial"].EIGHTBITS = 8
    sys.modules["serial"].PARITY_NONE = "N"

    sys.path.insert(0, os.path.join(repo, "FUGMCP"))
    try:
        import tango
        import importlib
        importlib.import_module("FUGMCP.FUGMCP")
        module = sys.modules["FUGMCP.FUGMCP"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2

    print("\n_reply_prefix derives what each command should answer")
    prefix = module.FUGMCP._reply_prefix
    check("query with a space  '>M0 ?'", prefix(b">M0 ?\n"), b"M0:")
    check("query without one   '>BON?'", prefix(b">BON?\n"), b"BON:")
    check("three-letter query  '>DIR ?'", prefix(b">DIR ?\n"), b"DIR:")
    check("setting command     '>S0 12.5'", prefix(b">S0 12.500000\n"), b"E")
    check("output command      '>BON 1'", prefix(b">BON 1\n"), b"E")
    check("'*IDN?' is unpredictable", prefix(b"*IDN?\n"), None)

    print("\nA clean exchange still works, and drains first")
    stub = StubSerial(script=[[b"M0:619.000\n"]])
    dev = build(module, stub)
    check("Voltage", dev.read_Voltage(), 619.0)
    check("wrote the query", stub.written, [b">M0 ?\n"])
    check("drained before writing", stub.drains, 1)

    print("\nThe hv2 failure: a stale reply left in the port")
    # Without the drain, read_Voltage returns 984.429774 -- the answer to the
    # PREVIOUS command -- and nothing anywhere notices, because it parses.
    stub = StubSerial(script=[[b"M0:619.000\n"]],
                      stale=[b"S0:984.429774\n"])
    dev = build(module, stub)
    check("reads its own answer, not the stale one",
          dev.read_Voltage(), 619.0)

    print("\nThe echo of the command is skipped, not mistaken for a reply")
    stub = StubSerial(script=[[b">S0 984.429774\n", b"E0\n"]])
    dev = build(module, stub)
    dev.write_SetVoltage(984.429774)
    check("no FAULT", dev.state, None)
    check("status untouched", dev.statustext, "")

    print("\nA reply that answers a different command triggers one retry")
    stub = StubSerial(script=[[b"S0:984.429774\n"], [b"M0:619.000\n"]])
    dev = build(module, stub)
    check("second attempt gets the right answer", dev.read_Voltage(), 619.0)
    check("wrote twice", stub.written, [b">M0 ?\n", b">M0 ?\n"])
    check("drained before each write", stub.drains, 2)

    print("\nSilence raises instead of returning an empty line")
    # The old code returned b"" here, and float(b""[3:-1]) raised ValueError
    # somewhere far away with nothing in it about the serial port.
    stub = StubSerial(script=[[], []])
    dev = build(module, stub)
    try:
        dev.read_Voltage()
        check("raised", False, True)
    except tango.DevFailed as exc:
        text = str(exc)
        check("raised DevFailed", True, True)
        check("names the port", "/dev/stub" in text, True)
        check("names the command", "M0" in text, True)
    check("tried twice before giving up", len(stub.written), 2)

    print("\nA genuine refusal from the supply reaches the caller")
    # 'E1' is the supply saying no. It matches the expected 'E' prefix, so it
    # is returned rather than retried, and the caller's own check turns it
    # into the FAULT it always did -- but now with a message that means it.
    stub = StubSerial(script=[[b"E1\n"]])
    dev = build(module, stub)
    dev.write_SetVoltage(1400.0)
    check("FAULT", dev.state, tango.DevState.FAULT)
    check("status carries the refusal", "E1" in dev.statustext, True)
    check("not retried", len(stub.written), 1)

    print("\nsendCommand keeps working for arbitrary commands")
    stub = StubSerial(script=[[b"anything at all\n"]])
    dev = build(module, stub)
    check("returns whatever came back",
          dev._txn(b">XYZ ?\n", validate=False), b"anything at all\n")
    check("still drained", stub.drains, 1)

    print("\nA closed port is refused before any I/O")
    dev = build(module)
    dev.ser = None
    try:
        dev._txn(b">M0 ?\n")
        check("raised", False, True)
    except tango.DevFailed:
        check("raised DevFailed", True, True)

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
