#!/usr/bin/env python3
"""Regression tests for HuttingerPFGDC's start-up and frame handling.

sputtering/power/magDC was connected for the first time on 30-oct-2026 and
came up FAULT with:

    No usable answer on /dev/serial/...: unpack requires a buffer of 5 bytes

Three separate problems, found in that order:

  1. The cable had no null-modem adapter, so nothing was arriving at all.
     That is hardware, and it is fixed -- but the message blamed a buffer
     length, naming neither the port nor the command nor the fact that the
     reply was empty. parse_response called struct.unpack on whatever came
     back; b"" is what a silent instrument returns, so that was the likely
     input, not the exotic one.

  2. init_device opened with two WRITE commands: 4E (set control mode) with
     data 4, and 4F (set operating state) with data 0. The second switches
     the output off, so starting the server -- or an Init from Jive --
     dropped a generator somebody might be using. HuttingerPFGRF, which has
     always worked, opens with a single CE query instead.

  3. The control mode written was 4 = REMOTE1, which is control over the I/O
     connector. Driving it over the serial line wants 3 = RS232 (manual,
     table 8.12, row N).

The frames here are the ones the real PFG-DC returned that day, so the
checksum arithmetic is pinned against the instrument and not against a
reading of the manual.

Everything runs against a stub serial port. No generator is contacted.

Usage:  python3 tools/test_huttingerpfgdc.py [--root PATH]
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


def trama(cmd, data):
    """A 5-byte block with the XOR checksum the manual specifies."""
    m = bytes([0, cmd, (data >> 8) & 0xFF, data & 0xFF])
    crc = 0
    for b in m:
        crc ^= b
    return m + bytes([crc])


# Exactly what the generator answered on 30-oct-2026.
CE_MODO_REALTIME = bytes.fromhex("004e00024c")   # control mode = 2
CE_MODO_RS232 = bytes.fromhex("004e00034d")      # control mode = 3
CF_ESTADO_OFF = bytes.fromhex("004f00004f")      # operating state = 0
ACK = bytes.fromhex("0006000006")
NAK = trama(0x15, 0)


class StubSerial:
    """Serves a queue of replies, one per write."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.escrito = []

    def write(self, data):
        self.escrito.append(data)

    def read(self, n):
        if not self.respuestas:
            return b""
        return self.respuestas.pop(0)

    def reset_input_buffer(self):
        pass

    def close(self):
        pass


def build(module, respuestas):
    class Fake(module.HuttingerPFGDC):
        SerialPort = "/dev/stub"

        def __init__(self):
            self.state = None
            self.statustext = ""
            self.ser = None
            self.controlmode = None

        def set_state(self, s):
            self.state = s

        def get_state(self):
            return self.state

        def set_status(self, t):
            self.statustext = t

        def error_stream(self, *a):
            pass

        def debug_stream(self, *a):
            pass

    dev = Fake()
    # init_device replaces self.ser with whatever serial.Serial returns, so
    # the stub has to be what that factory hands back -- otherwise the test
    # keeps a reference to a port the device no longer uses.
    puerto = StubSerial(respuestas)
    dev.ser = puerto
    module.Device.init_device = lambda self: None
    module.serial.Serial = lambda *a, **kw: puerto
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

    sys.path.insert(0, os.path.join(repo, "HuttingerPFGDC"))
    try:
        import tango
        import importlib
        importlib.import_module("HuttingerPFGDC.HuttingerPFGDC")
        module = sys.modules["HuttingerPFGDC.HuttingerPFGDC"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2

    print("\nthe checksum arithmetic matches the real generator")
    dev = build(module, [])
    check("CE reply parses", dev.parse_response(CE_MODO_REALTIME),
          (0, "4e", 2))
    check("CF reply parses", dev.parse_response(CF_ESTADO_OFF), (0, "4f", 0))
    check("ACK is recognised", dev.parse_response(ACK)[1], "ACK")
    check("NAK is recognised", dev.parse_response(NAK)[1], "NACK")

    print("\nan empty reply says so, instead of blaming a buffer")
    # This is the 30-oct-2026 message, the one that sent us looking at
    # struct.unpack when the cable had no null-modem adapter.
    dev = build(module, [])
    try:
        dev.parse_response(b"")
        check("raised", False, True)
    except module.HuttingerError as exc:
        check("names the length", "got 0" in str(exc), True)
        check("no longer mentions a buffer", "buffer" in str(exc), False)

    print("\na short reply too")
    dev = build(module, [])
    try:
        dev.parse_response(b"\x00\x4e\x00")
        check("raised", False, True)
    except module.HuttingerError as exc:
        check("names the length", "got 3" in str(exc), True)

    print("\na corrupted frame is caught by the checksum")
    malo = bytearray(CE_MODO_REALTIME)
    malo[2] ^= 0xFF                       # flip a data byte, leave the crc
    dev = build(module, [])
    try:
        dev.parse_response(bytes(malo))
        check("raised", False, True)
    except module.HuttingerError as exc:
        check("says checksum", "checksum" in str(exc), True)

    print("\nstart-up ASKS, and commands nothing")
    dev = build(module, [CE_MODO_REALTIME])
    dev.init_device()
    check("state", dev.state, tango.DevState.OFF)
    check("exactly one exchange", len(dev.ser.escrito), 1)
    check("and it was the CE query", dev.ser.escrito[0][1], 0xCE)
    check("nothing was written to the generator",
          [w for w in dev.ser.escrito if w[1] < 0x80], [])

    print("\nand it reports a control mode that is not RS232")
    check("status names REALTIME", "REALTIME" in dev.statustext, True)
    check("and says commands will be refused",
          "refuse" in dev.statustext, True)
    check("mode recorded", dev.controlmode, 2)

    print("\nwith the generator already in RS232 it just says so")
    dev = build(module, [CE_MODO_RS232])
    dev.init_device()
    check("state", dev.state, tango.DevState.OFF)
    check("status", dev.statustext,
          "Connected to the PFG-DC, control mode RS232")

    print("\na silent generator faults, naming the port")
    dev = build(module, [])
    dev.init_device()
    check("FAULT", dev.state, tango.DevState.FAULT)
    check("names the port", "/dev/stub" in dev.statustext, True)

    print("\nSetRemoteControl writes 3, not 4, and reads it back")
    # 4 = REMOTE1 is the I/O connector; the serial line wants 3 = RS232.
    dev = build(module, [ACK, CE_MODO_RS232])
    salida = dev.do_set_remote_control()
    check("returns the mode in force", salida, "RS232")
    check("wrote 4E", dev.ser.escrito[0][1], 0x4E)
    check("with data 3, not 4", dev.ser.escrito[0][3], 3)
    check("then read it back with CE", dev.ser.escrito[1][1], 0xCE)
    check("mode recorded", dev.controlmode, 3)

    print("\nand it believes the read-back, not the write")
    # A refused write answers NAK and the mode stays as it was. Reporting
    # success there would be the worst outcome: the caller would think it had
    # control and every later command would quietly fail.
    dev = build(module, [NAK, CE_MODO_REALTIME])
    salida = dev.do_set_remote_control()
    check("says it was refused", salida.startswith("refused"), True)
    check("names the mode it stayed in", "REALTIME" in salida, True)
    check("status agrees", "refused" in dev.statustext, True)

    print("\nSetLocalControl hands the panel back, always to LOCAL")
    # LOCAL and not whatever it was before: REALTIME is one keypress away on
    # the front panel once it has control, so there is no state to remember.
    dev = build(module, [ACK, trama(0x4E, 1)])
    salida = dev.do_set_local_control()
    check("returns the mode in force", salida, "LOCAL")
    check("wrote 4E", dev.ser.escrito[0][1], 0x4E)
    check("with data 1 (LOCAL)", dev.ser.escrito[0][3], 1)
    check("read it back", dev.ser.escrito[1][1], 0xCE)
    check("mode recorded", dev.controlmode, 1)

    print("\nand it too believes the read-back")
    dev = build(module, [NAK, CE_MODO_RS232])
    salida = dev.do_set_local_control()
    check("says refused", salida.startswith("refused"), True)
    check("names where it stayed", "RS232" in salida, True)

    print("\nthe two commands are symmetric: remote then local")
    dev = build(module, [ACK, CE_MODO_RS232, ACK, trama(0x4E, 1)])
    check("to RS232", dev.do_set_remote_control(), "RS232")
    check("and back to LOCAL", dev.do_set_local_control(), "LOCAL")

    print("\ndelete_device still switches the output off, deliberately")
    # The opposite decision from init_device, and on purpose: a generator
    # left running with nothing watching it is the dangerous state.
    dev = build(module, [ACK])
    dev.delete_device()
    check("sent 4F", dev.ser.escrito[0][1], 0x4F)
    check("with data 0 (off)", dev.ser.escrito[0][3], 0)

    print("\nand survives a port that never opened")
    dev = build(module, [])
    dev.ser = None
    try:
        dev.delete_device()
        check("no exception", True, True)
    except Exception as exc:
        check("no exception", "%s: %s" % (type(exc).__name__, exc), True)

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
