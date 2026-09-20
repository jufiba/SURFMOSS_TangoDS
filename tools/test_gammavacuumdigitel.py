#!/usr/bin/env python3
"""Regression tests for GammaVacuumDigitel: State must be current without a
client ever reading a live attribute.

leem/vacuum/ColumnsIonPump and xps/vacuum/ionpump are both watched by
AlarmNotifier rules (alarm=ALARM,FAULT,OFF ok=ON), which only ever calls
State() and never reads an attribute. _read_hv_state() was the only thing
that re-derived ON/OFF/FAULT from a live query, and it used to run only from
_connect() and the On()/Off() commands -- a pump that tripped off by itself
in between kept reporting whatever it last was. Both instances happened to
have polled_attr set on a numeric attribute for an unrelated load-reduction
reason (docs/DS-architecture.md section 2), which was quietly the only thing
keeping the alarm honest. Fixed 20-Sep-2026 by having always_executed_hook
re-check the HV state on its own, rate-limited by _STATE_POLL_INTERVAL so a
burst of State() polls costs one Telnet exchange, not one each. See
GammaVacuumDigitel/README.md.

Everything runs against a stub socket. No controller is contacted.

Usage:  python3 tools/test_gammavacuumdigitel.py [--root PATH]
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
        print("  FAIL %-48s got %r want %r" % (what, got, want))
    else:
        print("  ok   %-48s %r" % (what, got))


class StubSocket:
    """Enough of socket.socket to drive _send_command's Telnet exchange.

    Replies are queued whole (e.g. b"OK 00 YES>") and consumed one per
    sendall(). The pre-command drain (recv(4096)) and _connect()'s own
    banner discard (recv(1024)) always report nothing pending -- this stub
    is for exercising always_executed_hook, not _connect()'s handshake.
    """

    def __init__(self):
        self.replies = []
        self.sent = []
        self._buf = b""

    def settimeout(self, t):
        pass

    def connect(self, addr):
        pass

    def sendall(self, data):
        self.sent.append(data)
        self._buf = self.replies.pop(0) if self.replies else b">"

    def recv(self, n):
        if n != 1:
            raise TimeoutError()          # drain / banner discard: nothing pending
        if not self._buf:
            raise TimeoutError()
        b, self._buf = self._buf[:1], self._buf[1:]
        return b

    def close(self):
        pass


def build(module, tango, sock=None):
    """The server with Device stubbed out and _connect()'s handshake
    skipped: dev._sock is set up already "connected", exactly as
    tools/test_itech6000c.py does for its own stub socket. _connect()'s own
    multi-exchange handshake is pre-existing, unchanged code, not part of
    this fix, so it is not exercised here.
    """

    class Fake(module.GammaVacuumDigitel):
        IP = "stub"
        Port = 23
        Supply = 1

        def __init__(self):
            self.state = tango.DevState.UNKNOWN
            self.status = ""

        def set_state(self, state):
            self.state = state

        def get_state(self):
            return self.state

        def set_status(self, status):
            self.status = status

        def error_stream(self, *a):
            pass

    dev = Fake()
    dev._sock = sock if sock is not None else StubSocket()
    dev._factor = None
    dev._last = 0.0
    dev._last_state_poll = 0.0
    dev._reports_relay = None
    dev.state = tango.DevState.ON
    return dev


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]

    sys.path.insert(0, os.path.join(repo, "GammaVacuumDigitel"))
    try:
        import tango
        import importlib
        importlib.import_module("GammaVacuumDigitel.GammaVacuumDigitel")
        module = sys.modules["GammaVacuumDigitel.GammaVacuumDigitel"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2

    print("\nState follows a live query from the hook alone, no attribute read")
    dev = build(module, tango)
    dev.state = tango.DevState.ON            # as if On() had been called earlier
    sock = dev._sock
    sock.replies = [b"OK 00 NO>"]             # the pump tripped off by itself
    dev.always_executed_hook()
    check("state follows the live HV query, no On()/Off() involved",
          dev.state, tango.DevState.OFF)
    check("one exchange", len(sock.sent), 1)

    print("\nrate-limited: a second dispatch inside the window asks nothing")
    sock.replies = [b"OK 00 YES>"]             # would flip back ON if asked
    dev.always_executed_hook()
    check("still OFF: too soon to re-poll", dev.state, tango.DevState.OFF)
    check("no new exchange", len(sock.sent), 1)

    print("\npast _STATE_POLL_INTERVAL, it asks again")
    dev._last_state_poll = time.time() - module._STATE_POLL_INTERVAL - 0.1
    dev.always_executed_hook()
    check("state follows the fresh query", dev.state, tango.DevState.ON)
    check("a second exchange happened", len(sock.sent), 2)

    print("\na failed query faults cleanly, does not raise")
    dev._last_state_poll = 0.0
    sock.replies = []                          # sendall() falls back to b">":
    # an empty/garbage reply -- no OK/ER, too short -- raises DigitelError,
    # which _read_hv_state() must turn into FAULT rather than let escape.
    dev.always_executed_hook()
    check("state", dev.state, tango.DevState.FAULT)
    check("status names the problem",
          "high voltage" in dev.status.lower(), True)

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
