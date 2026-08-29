#!/usr/bin/env python3
"""Regression tests for the WisselMCA transport: every read has a deadline.

Written after the second wedge of 29-Aug-2026. `hid.device.read(n)` with no
timeout waits for ever on a blocking handle, and the call runs inside the
device's Tango serialization monitor, so the whole device stops answering:
ping still replies while state() and every attribute come back IMP_LIMIT. A
gdb backtrace showed the thread parked in hid_read_timeout /
pthread_cond_wait, six hours after a clean restart, with no USB error in
dmesg -- one reply had gone missing, which is all it takes. Fourteen calls
were open to it.

This is a different fault from the one fixed earlier the same day, which was
the unbounded drain() spinning on a 50 ms timeout; that one showed as 0.7% CPU
in ppoll. Both are real and both wedge the device.

The card is driven through a stub, so nothing here reaches the instrument --
which matters: it is usually measuring, and these tests call cleardata(),
setmode(), start() and stop().

Usage:  python3 tools/test_wisselmca.py [--root PATH]
Exit:   0 all passed, 1 failures, 2 could not run.
"""

import os
import sys
import time

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAILS = 0


def check(what, got, want):
    global FAILS
    if got != want:
        FAILS += 1
        print("  FAIL %-46s got %r want %r" % (what, got, want))
    else:
        print("  ok   %-46s %r" % (what, got))


class Stub:
    """Enough of hid.device to drive cmca. Every read is recorded.

    mode:
        "answer"  reply correctly to each command
        "silent"  never answer, as a lost reply looks
        "wrong"   answer with a count byte that does not match
        "chatty"  never answer the command, but never go quiet either, so the
                  resynchronising drain cannot finish
    """

    # command byte -> (count byte, total reply length)
    REPLIES = {
        0xF1: (6, 7), 0x84: (3, 4), 0x04: (2, 3), 0x81: (4, 5),
        0x01: (2, 3), 0x13: (2, 3), 0x88: (12, 13), 0x08: (2, 3),
        0x92: (4, 5), 0x91: (6, 7), 0x90: (130, 131),
    }

    def __init__(self, mode="answer"):
        self.mode = mode
        self.reads = []          # (nbytes, timeout) for every read
        self.pending = None
        self.opened = None

    # --- the calls cmca makes ---
    def open(self, vid, pid):
        self.opened = (vid, pid)

    def open_path(self, path):
        self.opened = path

    def set_nonblocking(self, flag):
        pass

    def close(self):
        pass

    def write(self, message):
        self.pending = message[1]        # length byte first, then the command
        return len(message)

    def read(self, nbytes, timeout=None):
        self.reads.append((nbytes, timeout))
        if self.mode == "chatty":
            return [0] * 64
        if self.mode == "silent":
            return []
        if self.pending is None:
            return []                    # nothing outstanding: drain finds nothing
        count, length = self.REPLIES.get(self.pending, (0, 3))
        if self.mode == "wrong":
            count += 1
        self.pending = None
        return [count, 0] + [0] * (max(length, nbytes) - 2)


# Every cmca method that talks to the card, with arguments that reach the wire.
EXCHANGES = [
    ("model", ()),
    ("start", ()),
    ("stop", ()),
    ("readgeneral", ()),
    ("writegeneral", (0x0C00,)),
    ("setmode", (3,)),
    ("readmode", ()),
    ("cleardata", ()),
    ("readPHA", ()),
    ("readlastchannel", ()),
    ("readchannel", (17,)),
    ("readpage", (0,)),
]


def unwrap(result):
    """cmca replies as True, (True, value) or (False, message)."""
    if result is True:
        return True, None
    if result is False:
        return False, "no reply"
    return result[0], result[1] if len(result) > 1 else None


def run(module, mode):
    card = module.cmca()
    card.dev = Stub(mode)
    return card


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]

    sys.path.insert(0, os.path.join(repo, "WisselMCA"))
    try:
        import importlib
        # import_module, not "from WisselMCA import WisselMCA": the package's
        # __init__ re-exports the Device class under the same name, so the
        # attribute lookup hands back the class instead of the module.
        importlib.import_module("WisselMCA.WisselMCA")
        module = sys.modules["WisselMCA.WisselMCA"]
    except ImportError as exc:
        print("cannot import the server (%s); run this where PyTango and "
              "hid are installed" % exc)
        return 2

    print("\nevery read carries a deadline")
    card = run(module, "answer")
    for name, args_ in EXCHANGES + [("writePHA", None)]:
        if args_ is None:
            import numpy
            args_ = (numpy.zeros(5, dtype="<u2"),)
        getattr(card, name)(*args_)
    missing = [n for n, t in card.dev.reads if t is None]
    check("reads issued", len(card.dev.reads) > 12, True)
    check("reads with no timeout", missing, [])

    print("\na lost reply is reported, not waited for")
    for name, args_ in EXCHANGES:
        card = run(module, "silent")
        started = time.time()
        ok, msg = unwrap(getattr(card, name)(*args_))
        took = time.time() - started
        good = (not ok and "no reply" in str(msg)) or \
               (not ok and "short response" in str(msg))
        check("%s -> %s" % (name, str(msg)[:44]), (good, took < 5.0),
              (True, True))

    print("\na reply with the wrong count is reported")
    for name, args_ in EXCHANGES:
        card = run(module, "wrong")
        ok, msg = unwrap(getattr(card, name)(*args_))
        check("%s -> %s" % (name, str(msg)[:44]),
              not ok and "wrong count" in str(msg), True)

    print("\na card that will not go quiet says so, and does not hold on")
    card = run(module, "chatty")
    started = time.time()
    ok, msg = unwrap(card.readmode())
    took = time.time() - started
    check("readmode -> %s" % str(msg)[:60], not ok, True)
    check("says the drain could not finish", "did not go quiet" in str(msg),
          True)
    check("bounded by DRAIN_SECONDS", took < card.DRAIN_SECONDS + 2.0, True)

    print("\nthe normal path still works")
    card = run(module, "answer")
    ok, value = unwrap(card.readmode())
    check("readmode ok", ok, True)
    ok, value = unwrap(card.readgeneral())
    check("readgeneral ok", ok, True)
    ok, w = unwrap(card.readPHA())
    check("readPHA returns five words", (ok, len(w)), (True, 5))
    ok, page = unwrap(card.readpage(0))
    check("readpage returns 128 bytes", (ok, len(page)), (True, 128))

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
