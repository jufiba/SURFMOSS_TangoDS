#!/usr/bin/env python3
"""Regression tests for HuttingerPFGRF's frame handling.

sputtering/power/magRFmag has always worked, and that is the point: it has
the same parse_response as HuttingerPFGDC, which called struct.unpack on
whatever came back from the port. An empty reply -- what a silent instrument
returns -- raised

    unpack requires a buffer of 5 bytes

naming neither the port, nor the command, nor the fact that nothing had
arrived. The DC generator showed exactly that on 30-oct-2026, when it was
first connected with no null-modem adapter. This one never has, because its
cable has always worked. Same code, same defect; the difference was luck.

Only the framing is covered here. Unlike the DC driver, this one's
init_device already opens with a single CE query and commands nothing, so
there was nothing to fix there.

Everything runs against a stub serial port. No generator is contacted.

Usage:  python3 tools/test_huttingerpfgrf.py [--root PATH]
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


ACK = bytes.fromhex("0006000006")
NAK = trama(0x15, 0)
CE_MODO = trama(0x4E, 3)            # control mode query answered as 3 = RS232
D1_POTENCIA = trama(0x51, 250)      # 250 W of direct power


class StubSerial:
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
    class Fake(module.HuttingerPFGRF):
        SerialPort = "/dev/stub"

        def __init__(self):
            self.state = None
            self.statustext = ""
            self.ser = None

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

    sys.path.insert(0, os.path.join(repo, "HuttingerPFGRF"))
    try:
        import tango
        import importlib
        importlib.import_module("HuttingerPFGRF.HuttingerPFGRF")
        module = sys.modules["HuttingerPFGRF.HuttingerPFGRF"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2

    print("\ngood frames still parse")
    dev = build(module, [])
    check("a query reply", dev.parse_response(CE_MODO), (0, "4e", 3))
    check("a value", dev.parse_response(D1_POTENCIA), (0, "51", 250))
    check("ACK", dev.parse_response(ACK)[1], "ACK")
    check("NAK", dev.parse_response(NAK)[1], "NACK")

    print("\nan empty reply says so, instead of blaming a buffer")
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

    print("\nand a corrupted one is caught by the checksum")
    malo = bytearray(CE_MODO)
    malo[3] ^= 0xFF                   # flip a data byte, leave the crc
    dev = build(module, [])
    try:
        dev.parse_response(bytes(malo))
        check("raised", False, True)
    except module.HuttingerError as exc:
        check("says checksum", "checksum" in str(exc), True)

    print("\na silent generator faults, naming the port")
    dev = build(module, [])
    dev.init_device()
    check("FAULT", dev.state, tango.DevState.FAULT)
    check("names the port", "/dev/stub" in dev.statustext, True)

    print("\nstart-up asks and commands nothing (already true here)")
    dev = build(module, [CE_MODO])
    dev.init_device()
    check("state", dev.state, tango.DevState.OFF)
    check("one exchange", len(dev.ser.escrito), 1)
    check("and it was a query", dev.ser.escrito[0][1] >= 0x80, True)
    check("status reports the mode", "RS232" in dev.statustext, True)
    check("mode recorded", dev.controlmode, 3)

    print("\nand a mode that is not RS232 is reported as such")
    # The answer to CE was read and thrown away before 30-oct-2026, so a
    # generator in LOCAL looked identical to one ready to be driven.
    dev = build(module, [trama(0x4E, 1)])
    dev.init_device()
    check("state", dev.state, tango.DevState.OFF)
    check("status names LOCAL", "LOCAL" in dev.statustext, True)
    check("and warns commands will be refused",
          "refuse" in dev.statustext, True)

    print("\nSetRemoteControl / SetLocalControl, with the read-back")
    dev = build(module, [ACK, CE_MODO])
    check("to RS232", dev.do_set_remote_control(), "RS232")
    check("wrote data 3", dev.ser.escrito[0][3], 3)
    dev = build(module, [ACK, trama(0x4E, 1)])
    check("to LOCAL", dev.do_set_local_control(), "LOCAL")
    check("wrote data 1", dev.ser.escrito[0][3], 1)
    dev = build(module, [NAK, CE_MODO])
    check("a refused write is reported",
          dev.do_set_local_control().startswith("refused"), True)

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
