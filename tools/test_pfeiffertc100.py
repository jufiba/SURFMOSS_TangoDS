#!/usr/bin/env python3
"""Regression tests for what PfeifferTC100 says about itself.

On 16-nov-2026 xps/vacuum/turboPCH read ON -- the pump was running and
answering -- while its status said:

    No usable answer on /dev/serial/by-path/platform-3f980000.usb-usb-0:1.2:1.0-port0

a port the device no longer even used. The old pi-xps had died and been
replaced, the by-path names moved with the hardware, and the SerialPort
property had just been repointed at the adapter's by-id name. The Init after
that repoint worked: it opened the new port, asked parameter 010 and got an
answer. But the good path in init_device set only the state, never the status,
so the text left behind by the failed Init before it stood untouched.

That is the third device in this repo with the same defect, after
CenterOneGauge and LeyboldIG3. A device working perfectly and describing
itself as broken costs exactly as much time to chase as the reverse, and the
stale text here still named the port that had just been abandoned -- the one
thing most likely to send the next reader back to the wrong socket.

So the test that matters is the last one: fail, then succeed, and check that
nothing of the failure survives.

Everything runs against a stub serial port. No pump is contacted.

Usage:  python3 tools/test_pfeiffertc100.py [--root PATH]
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
    """sendcommand() drains, writes, and reads up to \\r; `respuestas` is the
    queue it hands back, in order. Once the queue is empty a read returns the
    empty string, which is what a silent or unplugged pump produces."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.escrito = []
        self.drenajes = 0

    def reset_input_buffer(self):
        self.drenajes += 1

    def write(self, data):
        self.escrito.append(data)

    def read_until(self, sep):
        if not self.respuestas:
            return b""
        return self.respuestas.pop(0).encode("ascii")

    def close(self):
        pass


def crc(a):
    return sum(ord(c) for c in a) % 256


def trama(parameter, data, address="001", action="10"):
    """A well-formed reply frame, checksum included."""
    body = address + action + parameter + "%02d" % len(data) + data
    return body + "%03d" % crc(body) + "\r"


# The pump station switch, parameter 010, is a six-character boolean.
EN_MARCHA = trama("010", "111111")
PARADA = trama("010", "000000")


def build(module, respuestas):
    class Fake(module.PfeifferTC100):
        SerialPort = "/dev/stub"

        def __init__(self):
            self.state = None
            self.statustext = ""
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

    module.Device.init_device = lambda self: None
    dev = Fake()
    enchufa(module, dev, respuestas)
    return dev


def enchufa(module, dev, respuestas):
    """Point the serial factory at a fresh stub.

    init_device replaces self.ser with whatever serial.Serial returns, so the
    stub has to be what that factory hands back -- otherwise the test keeps a
    reference to a port the device no longer uses. Separate from build() so a
    second init_device on the same device can be given a different port, which
    is exactly the repoint-and-Init case this file exists for.
    """
    puerto = StubSerial(respuestas)
    dev.ser = puerto
    module.serial.Serial = lambda *a, **kw: puerto
    return puerto


def no_abre(module, dev):
    """Make the next init_device fail at the open, as a vanished port does."""
    def falla(*a, **kw):
        raise module.serial.SerialException("No such file or directory")
    module.serial.Serial = falla


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

    sys.path.insert(0, os.path.join(repo, "PfeifferTC100"))
    try:
        import tango
        import importlib
        importlib.import_module("PfeifferTC100.PfeifferTC100")
        module = sys.modules["PfeifferTC100.PfeifferTC100"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2

    print("\na port that cannot be opened faults, naming the port")
    dev = build(module, [])
    no_abre(module, dev)
    dev.init_device()
    check("FAULT", dev.state, tango.DevState.FAULT)
    check("names the port", "/dev/stub" in dev.statustext, True)
    check("says it could not open it",
          "Can't open" in dev.statustext, True)

    print("\na silent pump faults, and does not die trying")
    dev = build(module, [])
    dev.init_device()
    check("FAULT", dev.state, tango.DevState.FAULT)
    check("No usable answer", "No usable answer" in dev.statustext, True)
    check("names the port", "/dev/stub" in dev.statustext, True)

    print("\na running pump: state AND status, both")
    dev = build(module, [EN_MARCHA])
    dev.init_device()
    check("ON", dev.state, tango.DevState.ON)
    check("the status says so", "Pump station on" in dev.statustext, True)
    check("and names the port it is answering on",
          "/dev/stub" in dev.statustext, True)
    check("one exchange, and the buffer was drained first",
          (len(dev.ser.escrito), dev.ser.drenajes), (1, 1))

    print("\na stopped pump is OFF, and says that")
    dev = build(module, [PARADA])
    dev.init_device()
    check("OFF", dev.state, tango.DevState.OFF)
    check("the status says so", "Pump station off" in dev.statustext, True)
    check("not the other one", "Pump station on" in dev.statustext, False)

    print("\na reply for another parameter is out of step, not a reading")
    dev = build(module, [trama("312", "000100")])
    dev.init_device()
    check("FAULT", dev.state, tango.DevState.FAULT)
    check("the status says which", "out of step" in dev.statustext, True)

    print("\nfail, then succeed: nothing of the failure may survive")
    # This is xps/vacuum/turboPCH on 16-nov-2026, and the only case here that
    # would have failed against the previous code: the port is repointed and
    # Init run again, so the second init_device opens a different stub.
    dev = build(module, [])
    dev.init_device()                        # the failure
    viejo = dev.statustext
    check("starts out FAULT", dev.state, tango.DevState.FAULT)
    enchufa(module, dev, [EN_MARCHA])
    dev.init_device()                        # and the recovery
    check("ON", dev.state, tango.DevState.ON)
    check("the status no longer mentions the failure",
          "No usable answer" in dev.statustext, False)
    check("and it really changed", dev.statustext != viejo, True)

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
