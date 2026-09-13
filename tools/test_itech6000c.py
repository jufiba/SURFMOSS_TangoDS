#!/usr/bin/env python3
"""Regression tests for Itech6000C's deadman, Keepalive and I/O lock.

vsm/safety/interlockmagnetwater guards the VSM magnet's cooling water and
commands vsm/power/coilcurrent2, an Itech6000C. The supply had no Keepalive
command at all, so the interlock -- which sends one on every cycle while the
permissive is granted -- went to FAULT one cycle after granting. Adding a
Keepalive that does nothing would have silenced that and protected nothing,
so the deadman comes with it: the supply switches its own output off if the
keepalives stop, which is what covers the interlock's Pi dying.

The I/O lock is part of the same change and not optional. Every read here
was a bare send() followed by recv(1024) on the shared socket, and the
deadman thread runs outside Tango's serialization monitor: without the lock
its "OUTPUT OFF" interleaves with a client's half-finished query and both
read the wrong answer, on the supply that feeds the magnet.

Everything runs against a stub socket. No supply is contacted.

Usage:  python3 tools/test_itech6000c.py [--root PATH]
Exit:   0 all passed, 1 failures, 2 could not run.
"""

import os
import sys
import threading
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
    """Enough of socket.socket to drive _send/_ask.

    `busy` is set by send and cleared by recv, so a second exchange starting
    before the first has read its reply is recorded in `overlap`. Only
    meaningful for _ask traffic: a _send carries no reply and leaves busy set
    on purpose, so the concurrency test uses queries only.
    """

    def __init__(self, reply=b"1\n", delay=0.0):
        self.reply = reply
        self.delay = delay
        self.sent = []
        self.busy = False
        self.overlap = False

    def send(self, data):
        self.sent.append(data)
        if self.busy:
            self.overlap = True
        self.busy = True
        if self.delay:
            time.sleep(self.delay)

    def recv(self, n):
        if self.delay:
            time.sleep(self.delay)
        self.busy = False
        return self.reply

    def close(self):
        pass


def build(module, timeout=0.0, sock=None):
    """The server with Device stubbed out and the socket replaced."""

    class Fake(module.Itech6000C):
        IP = "stub"
        Port = 0
        Timeout = 1.0
        DeadmanTimeout = timeout

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
    dev.s = sock if sock is not None else StubSocket()
    dev.ItechConnected = True
    dev._io_lock = threading.Lock()
    dev._deadman = None
    dev._last_keepalive = time.monotonic()
    dev._output_asserted = False
    dev._deadman_tripped = False
    return dev


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]

    sys.path.insert(0, os.path.join(repo, "Itech6000C"))
    try:
        import tango
        import importlib
        importlib.import_module("Itech6000C.Itech6000C")
        module = sys.modules["Itech6000C.Itech6000C"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2

    print("\nKeepalive refreshes the timer and touches nothing else")
    dev = build(module)
    dev._last_keepalive = time.monotonic() - 5.0
    dev.do_keepalive()
    check("timer refreshed", dev.read_TimeSinceKeepalive() < 0.5, True)
    check("nothing was sent to the supply", dev.s.sent, [])
    check("output state untouched", dev._output_asserted, False)

    print("\nOutputOn arms the deadman, OutputOff disarms it")
    dev = build(module)
    dev.do_output_on()
    check("output asserted", dev._output_asserted, True)
    check("state", dev.state, tango.DevState.ON)
    check("sent", dev.s.sent, [b"OUTPUT ON\n"])
    dev._deadman_tripped = True
    dev.do_output_on()
    check("OutputOn clears a previous trip", dev._deadman_tripped, False)
    dev.do_output_off()
    check("output no longer asserted", dev._output_asserted, False)
    check("state", dev.state, tango.DevState.OFF)

    print("\nthe deadman switches the output off when keepalives stop")
    dev = build(module, timeout=0.2)
    dev.do_output_on()
    dev.s.sent = []
    dev._deadman = module._Deadman(dev)
    dev._deadman.start()
    time.sleep(0.6)
    dev._deadman.stop.set()
    check("OUTPUT OFF sent", b"OUTPUT OFF\n" in dev.s.sent, True)
    check("tripped", dev._deadman_tripped, True)
    check("state", dev.state, tango.DevState.OFF)
    check("status says why", dev.statustext.startswith("Deadman expired"), True)
    check("DeadmanTripped attribute", dev.read_DeadmanTripped(), True)

    print("\na keepalive every cycle keeps it alive")
    dev = build(module, timeout=0.4)
    dev.do_output_on()
    dev.s.sent = []
    dev._deadman = module._Deadman(dev)
    dev._deadman.start()
    for _ in range(8):
        time.sleep(0.1)
        dev.do_keepalive()
    dev._deadman.stop.set()
    check("never tripped", dev._deadman_tripped, False)
    check("nothing sent", dev.s.sent, [])
    check("state still ON", dev.state, tango.DevState.ON)

    print("\nthe deadman ignores an output that is not asserted")
    dev = build(module, timeout=0.2)
    dev._deadman = module._Deadman(dev)
    dev._deadman.start()
    time.sleep(0.5)
    dev._deadman.stop.set()
    check("nothing sent", dev.s.sent, [])
    check("not tripped", dev._deadman_tripped, False)

    print("\nthe lock keeps the deadman out of a client's exchange")
    sock = StubSocket(delay=0.02)
    dev = build(module, sock=sock)
    dev._output_asserted = True

    def reader():
        for _ in range(15):
            dev._ask(b"MEASure:SCALar:VOLTAGE:DC?\n")

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check("no exchange overlapped another", sock.overlap, False)
    check("every query was sent", len(sock.sent), 60)

    print("\na closed link raises instead of sending on a dead socket")
    dev = build(module)
    dev.ItechConnected = False
    for name, call in (("_send", lambda: dev._send(b"OUTPUT OFF\n")),
                       ("_ask", lambda: dev._ask(b"OUTPUT?\n"))):
        try:
            call()
            check("%s raises when disconnected" % name, "no exception", "raise")
        except Exception as e:
            check("%s raises when disconnected" % name,
                  "NotConnected" in str(e) or "no link" in str(e), True)

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
