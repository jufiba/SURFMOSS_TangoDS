#!/usr/bin/env python3
"""Regression tests for LEEMmacros' image wait and its counter file.

Two faults, both found in November 2026:

  every acquisition waited for an image with a bare

      uview.AcquireSingleImage()
      while (uview.ContinousAcquisition):
          pass

  twelve times over. The read sends UView's "aip" over its single socket, so
  that loop asked as fast as CORBA and TCP allowed, had no timeout -- a
  wedged UView stopped an ARRES run silently and for ever on 20-Nov-2026 --
  and never polled leem_checkstop(), so the GUI Stop button could not
  interrupt it;

  leemSetDailyFolder() wrote macros.dat with three fields where
  leem_getfolder() unpacks four, leaving a counter file the next call could
  not read at all.

Everything runs against a stub tango module and a temporary counter file, so
no device server is contacted and the instrument is not touched. That is
also why this can run on a laptop, unlike the device-server tests here.

Usage:  python3 tools/test_leemmacros.py [--root PATH]
Exit:   0 all passed, 1 failures, 2 could not run.
"""

import io
import os
import shutil
import sys
import tempfile
import time
import types
from contextlib import redirect_stdout

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAILS = 0


def check(what, got, want):
    global FAILS
    if got != want:
        FAILS += 1
        print("  FAIL %-46s got %r want %r" % (what, got, want))
    else:
        print("  ok   %-46s %r" % (what, got))


def check_true(what, got):
    check(what, bool(got), True)


class FakeUview:
    """Enough of the Uview proxy for leem_acquire_and_wait.

    `busy_seconds` holds the image "unfinished" for that much wall clock,
    which is what a real exposure looks like from here; `busy_reads` holds it
    for a fixed number of questions instead. `reads` counts the questions,
    which is the whole point of the 50 ms poll.
    """

    def __init__(self, busy_seconds=0.0, busy_reads=0):
        self.busy_seconds = busy_seconds
        self.busy_reads = busy_reads
        self.reads = 0
        self.triggers = 0
        self.started = None

    def AcquireSingleImage(self):
        self.triggers += 1
        self.started = time.monotonic()

    @property
    def ContinousAcquisition(self):
        self.reads += 1
        if self.busy_reads > 0:
            self.busy_reads -= 1
            return 1
        if self.busy_seconds and self.started is not None:
            if time.monotonic() - self.started < self.busy_seconds:
                return 1
        return 0


def load(repo):
    """LEEMmacros with tango stubbed out before import.

    The module builds DeviceProxies at import time (a documented rough
    edge), so the stub has to be in place first or importing it would reach
    for the instrument.
    """
    tango = types.ModuleType("tango")

    class FakeProxy:
        def __init__(self, *a, **kw):
            pass

        def __getattr__(self, name):
            return 0.0

    tango.DeviceProxy = FakeProxy
    tango.ApiUtil = types.SimpleNamespace(cleanup=lambda: None)
    sys.modules["tango"] = tango

    sys.path.insert(0, os.path.join(repo, "scripts"))
    import LEEMmacros
    return LEEMmacros


def wait_tests(M):
    print("\nthe wait asks UView a few times, not as fast as it can")
    M.uview = FakeUview(busy_seconds=0.5)
    M.LEEM_POLL_IMAGE = 0.05
    start = time.monotonic()
    M.leem_acquire_and_wait()
    took = time.monotonic() - start
    check("triggered exactly once", M.uview.triggers, 1)
    check_true("waited for the image (>=0.5 s)", took >= 0.5)
    check_true("and not much longer (<1.0 s)", took < 1.0)
    # ~11 at 50 ms over 0.5 s. The bare busy-wait did one per round trip,
    # which is hundreds over the same exposure.
    check_true("asked ~10 times, not hundreds (%d)" % M.uview.reads,
               3 <= M.uview.reads <= 30)

    print("\nan image already finished costs one question and no sleep")
    M.uview = FakeUview()
    start = time.monotonic()
    M.leem_acquire_and_wait()
    check("one question", M.uview.reads, 1)
    check_true("returned at once", time.monotonic() - start < 0.05)

    print("\npast the warning time it says so and keeps waiting")
    M.uview = FakeUview(busy_seconds=0.45)
    M.LEEM_POLL_IMAGE = 0.02
    M.LEEM_WARN_IMAGE = 0.1
    out = io.StringIO()
    with redirect_stdout(out):
        M.leem_acquire_and_wait("throw-away")       # must NOT raise
    text = out.getvalue()
    check_true("warned at least once", text.count("WARNING") >= 1)
    check_true("warned more than once while it lasted",
               text.count("WARNING") >= 2)
    check_true("names what it is waiting for", "throw-away" in text)
    check_true("says it is still waiting", "Still waiting" in text)
    check_true("points at the UView window",
               "WaitForSingleObject" in text)
    check("it returned rather than raising", M.uview.triggers, 1)
    M.LEEM_WARN_IMAGE = 60.0

    print("\na GUI stop interrupts the wait, which it could not before")
    M.uview = FakeUview(busy_seconds=5.0)
    M.leem_abort.set()
    start = time.monotonic()
    try:
        M.leem_acquire_and_wait()
        check("raised KeyboardInterrupt", False, True)
    except KeyboardInterrupt:
        check("raised KeyboardInterrupt", True, True)
    check_true("did not sit out the 5 s", time.monotonic() - start < 1.0)
    M.leem_abort.clear()


def counter_tests(M):
    print("\nleemSetDailyFolder leaves a counter file that can be read back")
    tmp = tempfile.mkdtemp(prefix="leemmacros-test-")
    try:
        prefix = os.path.join(tmp, "Superficies")
        os.mkdir(prefix)
        M.counter_filename = os.path.join(tmp, "macros.dat")
        today = M.date.today()
        dayfolder = "%04d%02d%02d" % (today.year, today.month, today.day)

        with open(M.counter_filename, "w") as handle:
            handle.write("W:\\Superficies,%s,20200101,15" % prefix)
        out = io.StringIO()
        with redirect_stdout(out):
            M.leemSetDailyFolder()
        check_true("day folder created",
                   os.path.isdir(os.path.join(prefix, dayfolder)))
        # This is what used to raise ValueError: not enough values to unpack.
        check("leem_getfolder round-trips", M.leem_getfolder(),
              ("W:\\Superficies", prefix, dayfolder, 0))

        print("\nand the next acquisition still works off that file")
        with redirect_stdout(io.StringIO()):
            wfull, full, name = M.leem_makenextfolder_and_inc()
        check("first experiment of the day is _000", name, "000")
        check_true("wfull keeps the windows prefix",
                   wfull.startswith("W:\\Superficies"))
        check("counter advanced", M.leem_getfolder()[3], 1)

        print("\na day rollover still restarts the count")
        with open(M.counter_filename, "w") as handle:
            handle.write("W:\\Superficies,%s,20200101,15" % prefix)
        shutil.rmtree(os.path.join(prefix, dayfolder))
        with redirect_stdout(io.StringIO()):
            wfull, full, name = M.leem_makenextfolder_and_inc()
        check("new day restarts at _000", name, "000")
        check("file still has four fields",
              len(open(M.counter_filename).read().split(",")), 4)
    finally:
        shutil.rmtree(tmp)


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]

    try:
        M = load(repo)
    except ImportError as exc:
        print("cannot import LEEMmacros (%s); needs numpy and matplotlib" % exc)
        return 2

    wait_tests(M)
    counter_tests(M)

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
