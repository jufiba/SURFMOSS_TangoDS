#!/usr/bin/env python3
"""Regression tests for what LeyboldIG3 says about itself.

The same defect CenterOneGauge had, in three places and one degree worse.
Only the failing paths wrote anything, so:

  * read_Pressure on success set neither state nor status. One bad exchange
    put the device in FAULT and nothing could ever take it out: the gauge
    recovered, the readings recovered, and the device went on publishing
    FAULT -- which is the value AnalogInterlock and AlarmNotifier act on --
    until somebody restarted the server. In CenterOneGauge the stale half was
    only the status text; here it was the state.

  * Start and Stop set the state on success but left the status saying
    whatever the last refusal had said.

OFF is not a fault in this gauge: it is a hot-cathode gauge and OFF means the
filament is off, which is why read_Pressure returns INVALID early in that
state. The fix must not paper over that, so the ON written by a successful
read can only be reached from ON or FAULT -- never from OFF, which returns
before the exchange.

Everything runs against a stub serial port. No gauge is contacted.

Usage:  python3 tools/test_leyboldig3.py [--root PATH]
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


def trama(primero, cuerpo=b""):
    """Una trama del IG3: STX, longitud, cuerpo, suma de control."""
    d = bytes([primero]) + cuerpo
    return bytes([2, len(d)]) + d + bytes([sum(d) % 256])


def ack(texto=b""):
    return trama(0x06, texto)


def nak(texto=b"algo"):
    return trama(0x15, texto)


class StubSerial:
    """Sirve una cola de tramas byte a byte, como hace response()."""

    def __init__(self, tramas):
        self.buffer = b"".join(tramas)
        self.escrito = []

    def write(self, data):
        self.escrito.append(data)

    def read(self, n):
        out, self.buffer = self.buffer[:n], self.buffer[n:]
        return out

    def close(self):
        pass


def build(module, tramas, estado=None):
    class Fake(module.LeyboldIG3):
        SerialPort = "/dev/stub"
        Speed = 9600

        def __init__(self):
            self.state = estado
            self.statustext = ""

        def set_state(self, s):
            self.state = s

        def get_state(self):
            return self.state

        def set_status(self, text):
            self.statustext = text

        def error_stream(self, *a):
            pass

        def debug_stream(self, *a):
            pass

    dev = Fake()
    dev.ser = StubSerial(tramas)
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

    sys.path.insert(0, os.path.join(repo, "LeyboldIG3"))
    try:
        import tango
        import importlib
        importlib.import_module("LeyboldIG3.LeyboldIG3")
        module = sys.modules["LeyboldIG3.LeyboldIG3"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2

    ON = tango.DevState.ON
    OFF = tango.DevState.OFF
    FAULT = tango.DevState.FAULT

    print("\na good read reports the pressure and when it was read")
    dev = build(module, [ack(b"2.5E-09")], estado=ON)
    check("valor", dev.read_Pressure(), 2.5e-09)
    check("estado", dev.state, ON)
    check("el status nombra la presion", "2.5e-09 mbar" in dev.statustext, True)

    print("\nFAULT is not permanent: a good read takes it out")
    # Este es el caso grave. Contra el codigo anterior el estado se quedaba en
    # FAULT para siempre, publicando averia mientras el medidor media bien.
    dev = build(module, [ack(b"2.5E-09")], estado=FAULT)
    dev.statustext = "Can't read the pressure: no reply"
    check("vuelve a leer", dev.read_Pressure(), 2.5e-09)
    check("y sale del FAULT", dev.state, ON)
    check("el status ya no habla del fallo",
          "no reply" in dev.statustext, False)

    print("\nOFF is the filament, not a fault: no exchange, INVALID, untouched")
    dev = build(module, [], estado=OFF)
    valor = dev.read_Pressure()
    check("INVALID", valor[2], tango.AttrQuality.ATTR_INVALID)
    check("sigue OFF, no lo pisa un ON", dev.state, OFF)
    check("no ha hablado con el medidor", dev.ser.escrito, [])

    print("\na silent gauge is a fault, and says so")
    dev = build(module, [], estado=ON)
    valor = dev.read_Pressure()
    check("FAULT", dev.state, FAULT)
    check("INVALID, no un 0.0 creible", valor[2],
          tango.AttrQuality.ATTR_INVALID)
    check("el status lo explica", "no reply" in dev.statustext, True)

    print("\na refusal is a fault too")
    dev = build(module, [nak(b"R09")], estado=ON)
    valor = dev.read_Pressure()
    check("FAULT", dev.state, FAULT)
    check("INVALID", valor[2], tango.AttrQuality.ATTR_INVALID)
    check("el status cita el rechazo", "refused" in dev.statustext, True)

    print("\nStart says so, instead of keeping the old complaint")
    dev = build(module, [ack()], estado=OFF)
    dev.statustext = "IG3 refused: R09"
    dev.do_start()
    check("estado", dev.state, ON)
    check("status", dev.statustext, "Emission on")

    print("\nStop explains why Pressure will read INVALID from now on")
    dev = build(module, [ack()], estado=ON)
    dev.do_stop()
    check("estado", dev.state, OFF)
    check("el status dice que es el filamento",
          "filament is off" in dev.statustext, True)

    print("\ndelete_device survives a port that never opened")
    dev = build(module, [], estado=FAULT)
    dev.ser = None
    try:
        dev.delete_device()
        check("no revienta", True, True)
    except Exception as exc:
        check("no revienta", "%s: %s" % (type(exc).__name__, exc), True)

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
