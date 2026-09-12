#!/usr/bin/env python3
"""Regression tests for VarianTV301nav: framing validation on readcommand(),
and the errorCode window fix.

readcommand() trusted a `ser.read(nb)` reply outright: no length check, no
STX check, and no check that the reply named the window asked -- so a
lagging port could hand read_power's reply to read_temperature, both being 6
ASCII digits at the same offset, and it would parse silently. Every other
server in this family (LeyboldIG3, the Pfeiffer trio, GammaVacuumDigitel)
already guards this; this one did not, independent of any interlock -- no
AnalogInterlock uses this device as InputDevice.

Confirmed against the controller manual (Turbopump_Varian_TV301 NAVIGATOR_
Controller.pdf, "RS 232/RS 485 COMMUNICATION DESCRIPTION"): a read reply
mirrors the request -- STX ADDR WIN(3) COM DATA(n) ETX CRC(2) -- and the CRC
is the XOR of everything from ADDR through ETX, exactly what crc_code()
already computes for outgoing frames (hand-verified against the manual's own
worked example: window 000 write ON gives CRC 'B3', matching XOR(0x80, 0x30,
0x30, 0x30, 0x31, 0x31, 0x03) = 0xB3).

The same cross-check found read_errorCode reading window 125
(valveOperation's window, Logic/1 byte) instead of window 206 (Error code,
Numeric/6 bytes, an 8-bit fault mask) -- so errorCode never reported a fault
code, only ever 0 or 1 borrowed from the wrong window.

Everything here runs against a stub serial port. No controller is contacted.

Usage:  python3 tools/test_variantv301nav.py [--root PATH]
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
        print("  FAIL %-46s got %r want %r" % (what, got, want))
    else:
        print("  ok   %-46s %r" % (what, got))


class StubSerial:
    """Enough of serial.Serial to drive readcommand(). `chunk` is the bytes
    the next read() call returns; set it before each exchange."""

    def __init__(self, chunk=b""):
        self.chunk = chunk
        self.written = []
        self.flushed = 0

    def reset_input_buffer(self):
        self.flushed += 1

    def write(self, data):
        self.written.append(data)

    def read(self, n):
        return self.chunk[:n]


def build(module):
    class Fake(module.VarianTV301nav):
        def __init__(self):
            pass
    dev = Fake()
    dev.ser = StubSerial()
    return dev


def good_frame(dev, win, data, com=b'0'):
    """A well-formed reply: STX ADDR WIN COM DATA ETX CRC, checksummed with
    the server's own crc_code() -- the same function it uses to build
    outgoing frames, applied here to the reply."""
    body = b'\x02\x80' + win.encode("ascii") + com + data.encode("ascii") + b'\x03'
    return body + dev.crc_code(body).encode("ascii")


def readcommand_cases(module, VarianError):
    dev = build(module)

    print("\ncrc_code matches the manual's own worked example")
    # Command: START, window 000, write ON. Manual: CRC = 'B3'.
    cmd = bytes([0x02, 0x80]) + b"000" + b"1" + b"1" + bytes([0x03])
    check("crc_code(START/000/ON)", dev.crc_code(cmd).lower(), "b3")

    print("\na genuine reply is accepted and flushes the input first")
    dev.ser = StubSerial(good_frame(dev, "204", "000023"))
    check("value", dev.readcommand("204", 15), "000023")
    check("input buffer flushed before the write", dev.ser.flushed, 1)

    print("\nthe reply's CRC field may be upper or lower case hex")
    frame = good_frame(dev, "204", "000023")
    upper = frame[:-2] + frame[-2:].upper()
    dev.ser = StubSerial(upper)
    check("uppercase CRC still validates", dev.readcommand("204", 15),
          "000023")

    print("\nevery way a lagging or dead port can go wrong")

    def fails(label, chunk, contains):
        dev.ser = StubSerial(chunk)
        try:
            dev.readcommand("204", 15)
            check(label, "no exception raised", contains)
        except VarianError as e:
            check(label, contains in str(e), True)

    fails("empty (timeout, nothing)", b"", "short reply")
    fails("short reply", good_frame(dev, "204", "000023")[:9], "short reply")
    fails("no STX (garbage)", b"X" + good_frame(dev, "204", "000023")[1:],
          "does not start with STX")
    fails("reply for a different window (the defect)",
          good_frame(dev, "202", "000099"), "out of step")
    fails("reply is not a read reply (bad COM byte)",
          good_frame(dev, "204", "000023", com=b'1'), "not a read reply")
    frame = bytearray(good_frame(dev, "204", "000023"))
    frame[12] = 0x58  # clobber the ETX position
    fails("ETX missing where expected", bytes(frame), "no ETX")
    frame = bytearray(good_frame(dev, "204", "000023"))
    frame[-1] ^= 0x01  # flip a bit in the CRC
    fails("checksum mismatch", bytes(frame), "checksum mismatch")


def read_methods(module):
    dev = build(module)

    print("\nread_* methods parse the validated data field")
    dev.ser = StubSerial(good_frame(dev, "204", "000023"))
    check("read_temperature", dev.read_temperature(), 23)
    dev.ser = StubSerial(good_frame(dev, "205", "000005"))
    check("read_turboStatus", dev.read_turboStatus(), "Normal")
    dev.ser = StubSerial(good_frame(dev, "000", "1"))
    check("read_running True", dev.read_running(), True)
    dev.ser = StubSerial(good_frame(dev, "000", "0"))
    check("read_running False", dev.read_running(), False)

    print("\nread_errorCode now reads window 206, not 125")
    dev.ser = StubSerial(good_frame(dev, "206", "000021"))
    check("read_errorCode value", dev.read_errorCode(), 21)
    check("read_errorCode asked window 206",
          b"206" in dev.ser.written[-1], True)
    check("read_errorCode did not ask window 125",
          b"125" in dev.ser.written[-1], False)


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
    sys.modules["serial"].SerialException = type("SerialException", (Exception,), {})
    sys.modules["serial"].Serial = object
    sys.path.insert(0, os.path.join(repo, "VarianTV301nav"))
    try:
        import importlib
        importlib.import_module("VarianTV301nav.VarianTV301nav")
        module = sys.modules["VarianTV301nav.VarianTV301nav"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2

    readcommand_cases(module, module.VarianError)
    read_methods(module)

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
