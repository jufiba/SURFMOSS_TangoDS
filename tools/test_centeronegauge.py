#!/usr/bin/env python3
"""Regression tests for what CenterOneGauge says about itself.

leem/vacuum/gaugeEvap has now told two opposite lies from the same cause:
only the failing paths in read_Pressure wrote anything about the device, so
whatever the last failure left behind stood for ever.

First it was the state. The gauge was found reading 3.6 mbar at ATTR_VALID
with state OFF, and came back ON the instant it was restarted; that half was
fixed, and the docstring left behind the claim that "every path here sets the
state, in both directions".

Then it was the status, which outlived that fix. On 20-sep-2026 the gauge read
4.3 mbar at ATTR_VALID, state ON, while its status still said "The gauge did
not acknowledge PR1" -- left from a serial-port collision with the hygrometer
that had been resolved the previous evening. A device working perfectly and
describing itself as broken costs exactly as much time to chase as the
reverse, and here it cost a day of believing the gauge was still faulty.

So the test that matters is the third one: fail, then succeed, and check that
nothing of the failure survives.

Everything runs against a stub serial port. No gauge is contacted.

Usage:  python3 tools/test_centeronegauge.py [--root PATH]
Exit:   0 all passed, 1 failures, 2 could not run.
"""

import os
import sys
import types

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAILS = 0

ACK = "\x06"
BUENA = "0, 3.6000E+00\r\n"


def check(what, got, want):
    global FAILS
    if got != want:
        FAILS += 1
        print("  FAIL %-50s got %r want %r" % (what, got, want))
    else:
        print("  ok   %-50s %r" % (what, got))


class StubSerial:
    """sendcommand() escribe y lee hasta \\r\\n; `respuestas` es la cola que
    devuelve, en orden. Agotada la cola se devuelve cadena vacia, que es lo
    que produce una lectura que agota su tiempo."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.escrito = []

    def write(self, data):
        self.escrito.append(data)

    def read_until(self, sep):
        if not self.respuestas:
            return b""
        return self.respuestas.pop(0).encode("ascii")

    def close(self):
        pass


def build(module, respuestas):
    class Fake(module.CenterOneGauge):
        SerialPort = "/dev/stub"

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
    dev.ser = StubSerial(respuestas)
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

    sys.path.insert(0, os.path.join(repo, "CenterOneGauge"))
    try:
        import tango
        import importlib
        importlib.import_module("CenterOneGauge.CenterOneGauge")
        module = sys.modules["CenterOneGauge.CenterOneGauge"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2

    print("\na good read says what it read, and when")
    dev = build(module, [ACK, BUENA])
    valor = dev.read_Pressure()
    check("valor", valor, 3.6)
    check("estado", dev.state, tango.DevState.ON)
    check("el status nombra la presion", "3.6 mbar" in dev.statustext, True)
    check("y lleva fecha", "20" in dev.statustext, True)

    print("\nthe gauge not acknowledging PR1")
    dev = build(module, ["", ""])
    valor = dev.read_Pressure()
    check("FAULT", dev.state, tango.DevState.FAULT)
    check("calidad INVALID, no un 0.0 creible",
          valor[2], tango.AttrQuality.ATTR_INVALID)
    check("el status lo dice", "did not acknowledge" in dev.statustext, True)

    print("\nfail, then succeed: nothing of the failure may survive")
    # Este es el caso de gaugeEvap el 20-sep-2026, y el unico que habria
    # fallado contra el codigo anterior.
    #
    # Una lectura sin ACK consume UNA sola respuesta de la cola y vuelve: no
    # llega a mandar el ENQ. De ahi que aqui haya tres y no cuatro.
    dev = build(module, ["", ACK, BUENA])
    dev.read_Pressure()                      # el fallo
    viejo = dev.statustext
    valor = dev.read_Pressure()              # y la recuperacion
    check("vuelve a leer bien", valor, 3.6)
    check("estado ON", dev.state, tango.DevState.ON)
    check("el status ya NO habla del fallo",
          "did not acknowledge" in dev.statustext, False)
    check("y ha cambiado de verdad", dev.statustext != viejo, True)

    print("\nan answer that does not parse")
    dev = build(module, [ACK, "esto no es una medida\r\n"])
    valor = dev.read_Pressure()
    check("FAULT", dev.state, tango.DevState.FAULT)
    check("INVALID", valor[2], tango.AttrQuality.ATTR_INVALID)
    check("el status cita lo recibido",
          "Unreadable answer" in dev.statustext, True)

    print("\na measurement status other than 0 is not a reading")
    dev = build(module, [ACK, "4, 0.0000E+00\r\n"])
    valor = dev.read_Pressure()
    check("FAULT", dev.state, tango.DevState.FAULT)
    check("INVALID, no 0.0 a secas", valor[2],
          tango.AttrQuality.ATTR_INVALID)
    check("el status da el codigo para buscarlo",
          "status 4" in dev.statustext, True)

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
