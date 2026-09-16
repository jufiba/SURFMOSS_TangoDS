#!/usr/bin/env python3
"""Regression tests for the Hygrometer's identification handshake.

Three defects, all found on 16-sep-2026 while hunting for why
leem/safety/hygrometer would not come up:

  1. The expected identity was the literal string "Flood sensor above XPS",
     compiled into the server. There are two instances of this server, and
     the other one is over the LEEM: any board announcing itself honestly by
     its own name was rejected as an impostor, whatever it was. It is now the
     Identity property, defaulting to the XPS banner so that device keeps
     working untouched.

  2. 'id' was written with no terminator. The XPS board tolerates it; a
     sketch that reads a whole line before parsing never sees a complete
     command and stays silent for ever, which is indistinguishable from a
     dead board. Bare 'id' is still tried first -- the working board's
     behaviour does not change -- with 'id\\n' and 'id\\r\\n' as fallbacks.

  3. On every failure path the serial port was left open. A FAULTed
     hygrometer held /dev/ttyUSB2 while someone was re-cabling to find out
     why it had faulted.

Everything runs against a stub serial port. No board is contacted.

Usage:  python3 tools/test_hygrometer.py [--root PATH]
Exit:   0 all passed, 1 failures, 2 could not run.
"""

import os
import sys
import types

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAILS = 0


def check(what, got, want):
    global FAILS
    if got != want:
        FAILS += 1
        print("  FAIL %-50s got %r want %r" % (what, got, want))
    else:
        print("  ok   %-50s %r" % (what, got))


class StubSerial:
    """Enough of serial.Serial for the handshake.

    `replies` maps exactly what is written to what readline() then returns;
    anything not in it gets silence, which is what a board that never saw a
    complete command actually does.
    """

    def __init__(self, replies=None):
        self.replies = dict(replies or {})
        self.written = []
        self.closed = False
        self._pending = b""

    def reset_input_buffer(self):
        self._pending = b""

    def write(self, data):
        self.written.append(data)
        self._pending = self.replies.get(data, b"")

    def readline(self):
        out, self._pending = self._pending, b""
        return out

    def close(self):
        self.closed = True


class StubThread:
    """Stands in for ControlThread, which is not a daemon: starting the real
    one would keep the test interpreter alive at exit."""

    started = []

    def __init__(self, ds):
        self.ds = ds

    def start(self):
        StubThread.started.append(self.ds)


def build(module, stub, identity=None):
    class Fake(module.Hygrometer):
        SerialPort = "/dev/stub"
        Identity = (identity if identity is not None
                    else "Flood sensor above XPS")

        def __init__(self):
            self.state = None
            self.statustext = ""
            self.running = False
            self.ser = None

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
    # Device.init_device is what needs a real Tango device; skip just that.
    module.Device.init_device = lambda self: None
    module.serial.Serial = lambda *a, **kw: stub
    return dev


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]

    sys.modules.setdefault("serial", types.ModuleType("serial"))
    sys.modules["serial"].SerialException = type(
        "SerialException", (Exception,), {})
    sys.modules["serial"].Serial = object

    sys.path.insert(0, os.path.join(repo, "Hygrometer"))
    try:
        import tango
        import importlib
        importlib.import_module("Hygrometer.Hygrometer")
        module = sys.modules["Hygrometer.Hygrometer"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2

    module.ControlThread = StubThread

    print("\nthe XPS board, answering bare 'id' as it always has")
    stub = StubSerial({b"id": b"Flood sensor above XPS\r\n"})
    dev = build(module, stub)
    StubThread.started = []
    dev.init_device()
    check("state", dev.state, tango.DevState.ON)
    check("asked bare 'id' first", stub.written, [b"id"])
    check("reading thread started", len(StubThread.started), 1)
    check("port left open", stub.closed, False)

    print("\na board with its own name, and Identity set to match")
    stub = StubSerial({b"id": b"Flood sensor above LEEM\r\n"})
    dev = build(module, stub, identity="Flood sensor above LEEM")
    StubThread.started = []
    dev.init_device()
    check("state", dev.state, tango.DevState.ON)
    check("status names the board", "above LEEM" in dev.statustext, True)

    print("\nthe same board against the old hard-coded XPS identity")
    stub = StubSerial({b"id": b"Flood sensor above LEEM\r\n"})
    dev = build(module, stub)          # default Identity: the XPS banner
    StubThread.started = []
    dev.init_device()
    check("rejected", dev.state, tango.DevState.FAULT)
    check("status quotes what answered",
          "above LEEM" in dev.statustext, True)
    check("and says what it wanted",
          "above XPS" in dev.statustext, True)
    check("port closed", stub.closed, True)
    check("no reading thread", len(StubThread.started), 0)

    print("\na sketch that needs a terminator: bare 'id' is not enough")
    stub = StubSerial({b"id\n": b"Flood sensor above LEEM\r\n"})
    dev = build(module, stub, identity="Flood sensor above LEEM")
    StubThread.started = []
    dev.init_device()
    check("state", dev.state, tango.DevState.ON)
    check("tried bare first, then with LF", stub.written, [b"id", b"id\n"])
    check("status says which form answered",
          "id\\n" in dev.statustext.replace("'", ""), True)

    print("\nand one that wants CRLF")
    stub = StubSerial({b"id\r\n": b"Flood sensor above LEEM\r\n"})
    dev = build(module, stub, identity="Flood sensor above LEEM")
    dev.init_device()
    check("state", dev.state, tango.DevState.ON)
    check("all three forms tried in order", stub.written,
          [b"id", b"id\n", b"id\r\n"])

    print("\na silent board: says so, and lets go of the port")
    stub = StubSerial({})
    dev = build(module, stub)
    StubThread.started = []
    dev.init_device()
    check("FAULT", dev.state, tango.DevState.FAULT)
    check("says it is silence, not a wrong identity",
          "not talking" in dev.statustext, True)
    check("all three forms were tried", len(stub.written), 3)
    check("port closed", stub.closed, True)

    print("\nwhitespace around the property does not break the match")
    stub = StubSerial({b"id": b"  Flood sensor above LEEM  \r\n"})
    dev = build(module, stub, identity="  Flood sensor above LEEM ")
    dev.init_device()
    check("still recognised", dev.state, tango.DevState.ON)

    print("\ndelete_device stops the reader before closing under it")
    stub = StubSerial({b"id": b"Flood sensor above XPS\r\n"})
    dev = build(module, stub)
    dev.init_device()
    dev.delete_device()
    check("running cleared", dev.running, False)
    check("port closed", stub.closed, True)
    check("ser dropped", dev.ser, None)

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
