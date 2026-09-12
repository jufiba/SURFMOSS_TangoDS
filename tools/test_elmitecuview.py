#!/usr/bin/env python3
"""Regression tests for ElmitecUview: getROIdata() did not exist.

read_IntensityROI1/2 called self.getROIdata(1)/(2), a method never defined
anywhere in the file -- so both attributes raised AttributeError on every
read. Found live on leem/measurement/Uview:

    IntensityROI1: AttributeError: 'ElmitecUview' object has no attribute
    'getROIdata'

UView itself answers fine: queried directly through the device's own
sendCommand, "roi 1" / "roi 2" returned '0.350777' / '0.350592'. The protocol
is documented in Software_UViewScript.pdf, "ROIdata TCP": send "roi $ROIid",
receive "$value" (>=0.0, a reading) or a negative value / "ErrorCode $n" for
-1 intensity window not open, -2 ROI invalid, -3 ROI not active.

Everything here runs against a stub socket. UView is not contacted.

Usage:  python3 tools/test_elmitecuview.py [--root PATH]
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


class StubSocket:
    """Enough of socket.socket to drive TCPBlockingReceive/_send. `reply` is
    the next NUL-terminated string the read side serves, byte by byte."""

    def __init__(self, reply=b""):
        self.reply = reply
        self.pos = 0
        self.written = []

    def send(self, data):
        self.written.append(data)

    def recv(self, n):
        if self.pos >= len(self.reply):
            return b""
        b = self.reply[self.pos:self.pos + n]
        self.pos += n
        return b

    def close(self):
        pass


def build(module):
    class Fake(module.ElmitecUview):
        def __init__(self):
            pass
    dev = Fake()
    dev.ElmitecUviewConnected = True
    return dev


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]

    sys.path.insert(0, os.path.join(repo, "ElmitecUview"))
    try:
        import tango
        import importlib
        importlib.import_module("ElmitecUview.ElmitecUview")
        module = sys.modules["ElmitecUview.ElmitecUview"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2
    ElmitecUviewError = module.ElmitecUviewError

    print("\na genuine reading, as UView actually sends it")
    dev = build(module)
    dev.s = StubSocket(b"0.350777\x00")
    check("getROIdata(1)", dev.getROIdata(1), 0.350777)
    check("asked for the right ROI", dev.s.written, [b"roi 1"])

    print("\nread_IntensityROI1/2 no longer raise AttributeError")
    dev = build(module)
    dev.s = StubSocket(b"0.350777\x00")
    check("read_IntensityROI1", dev.read_IntensityROI1(), 0.350777)
    dev = build(module)
    dev.s = StubSocket(b"0.350592\x00")
    check("read_IntensityROI2", dev.read_IntensityROI2(), 0.350592)

    print("\nUView's documented error codes raise, not a bare negative number")

    def fails(label, reply, roiid, contains):
        dev = build(module)
        dev.s = StubSocket(reply)
        try:
            dev.getROIdata(roiid)
            check(label, "no exception raised", contains)
        except ElmitecUviewError as e:
            check(label, contains in str(e), True)

    fails("-1 intensity window not open", b"-1.000000\x00", 1,
          "intensity window is not open")
    fails("-2 ROI invalid", b"-2.000000\x00", 1, "ROI 1 is invalid")
    fails("-3 ROI not active", b"-3.000000\x00", 2, "ROI 2 is defined but "
          "not active")
    fails("literal ErrorCode text", b"ErrorCode -2\x00", 1, "ErrorCode -2")

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
