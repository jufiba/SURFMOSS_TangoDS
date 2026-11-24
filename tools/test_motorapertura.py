#!/usr/bin/env python3
"""Regression tests for MotorApertura: the protocol, and what it refuses.

The aperture has no limit switch and no encoder, so the two things that
matter are that a move is only ever believed when the board confirms it, and
that the server refuses what it cannot do safely rather than doing something
approximate. Specifically:

  a move is reported at the position the BOARD returns, never at the one
  this end expected, because a stepper that stalls still gets its pulses;

  a failed or unanswered move leaves the position INVALID rather than a
  number that would be read as a measurement;

  a second move while one is running is refused -- the board would queue it
  in its 64-byte serial buffer and run it afterwards;

  a board that does not identify itself is FAULT, not driven anyway: there
  is more than one Arduino on this lab's USB trees.

Everything runs against a stub serial port, so no board is contacted and
nothing moves. Needs PyTango, so it runs on a Pi or on wolframite.

Usage:  python3 tools/test_motorapertura.py [--root PATH]
Exit:   0 all passed, 1 failures, 2 could not run.
"""

import os
import queue
import sys
import threading
import time
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


def check_true(what, got):
    check(what, bool(got), True)


class StubSerial:
    """The Arduino sketch, in Python: enough of it to answer the protocol.

    `identity` and `fail_after` are the switches the tests need -- a board
    that is something else, and one that stops answering mid-run.
    """

    def __init__(self, identity="MotorApertura 1", position=0):
        self.identity = identity
        self.position = position
        self.timeout = 2.0
        self.sent = []
        self.replies = []
        self.fail_after = None        # stop answering after N commands
        self.answered = 0
        self.moves = []

    # --- the pyserial surface the server uses ---
    def reset_input_buffer(self):
        pass

    def close(self):
        pass

    def write(self, data):
        text = data.decode("ascii").strip()
        self.sent.append(text)
        if self.fail_after is not None and self.answered >= self.fail_after:
            return                                  # silence: no reply queued
        self.answered += 1
        self.replies.append(self._answer(text))

    def readline(self):
        if not self.replies:
            return b""                              # what a timeout looks like
        return (self.replies.pop(0) + "\n").encode("ascii")

    def _answer(self, text):
        if text == "I":
            return self.identity
        if text == "?":
            return "POS %d" % self.position
        if text == "Z":
            self.position = 0
            return "OK 0 0"
        if text == "H":
            return "ERR nohome"
        if text and text[0] in "+-":
            try:
                steps = int(text)
            except ValueError:
                return "ERR formato"
            self.moves.append(steps)
            self.position += steps
            return "OK %d %d" % (steps, self.position)
        return "ERR formato"


def build(module, tango, stub):
    """The server with the Device machinery stubbed out."""

    class Fake(module.MotorApertura):
        SerialPort = "stub"
        Baudrate = 9600
        MaxStepsPerMove = 20000
        StepsPerRevolution = 200
        PresetPositions = [0, 1000, 2000, 3000]

        def __init__(self):
            self.state = tango.DevState.UNKNOWN
            self.statustext = ""
            self.ser = stub
            self.lock = threading.Lock()
            self.jobs = queue.Queue()
            self.mover = None
            self.position = 0
            self.position_known = False

        def set_state(self, state):
            self.state = state

        def get_state(self):
            return self.state

        def set_status(self, text):
            self.statustext = text

        def get_name(self):
            return "leem/motion/apertura"

        def error_stream(self, *a):
            pass

        def debug_stream(self, *a):
            pass

    return Fake()


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]

    # A stub pyserial before the import, so this runs where it is absent.
    if "serial" not in sys.modules:
        stub = types.ModuleType("serial")
        stub.Serial = lambda *a, **kw: None
        stub.SerialException = Exception
        sys.modules["serial"] = stub

    sys.path.insert(0, os.path.join(repo, "MotorApertura"))
    try:
        import tango
        import importlib
        importlib.import_module("MotorApertura.MotorApertura")
        module = sys.modules["MotorApertura.MotorApertura"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2

    def wait_idle(dev, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            if dev.get_state() != tango.DevState.MOVING and dev.jobs.empty():
                return
            time.sleep(0.02)

    print("\na move is believed at the position the board reports")
    port = StubSerial(position=500)
    dev = build(module, tango, port)
    dev.position, dev.position_known = 500, True
    dev.set_state(tango.DevState.ON)
    dev.mover = module.MoveThread(dev)
    dev.mover.start()
    dev.queue_move(250)
    wait_idle(dev)
    check("the command sent", port.sent[-1], "+250")
    check("position from the board", dev.position, 750)
    check("state back to ON", dev.state, tango.DevState.ON)
    check("Position reads plainly", dev.read_Position(), 750)

    print("\nand at the board's number even if it is not the expected one")
    # A stalled stepper still gets its pulses, so the board is the authority.
    port.position = 700                      # the board disagrees
    dev.queue_move(100)
    wait_idle(dev)
    check("takes the board's answer, not 750+100", dev.position, 800)

    print("\na move nobody answers leaves the position INVALID")
    port.fail_after = port.answered          # from now on, silence
    dev.queue_move(10)
    wait_idle(dev, timeout=20.0)
    check("state", dev.state, tango.DevState.FAULT)
    check("Position is INVALID", dev.read_Position()[2],
          tango.AttrQuality.ATTR_INVALID)
    check_true("status says the position is lost",
               "no longer known" in dev.statustext)

    print("\na second move while one runs is refused, not queued")
    port2 = StubSerial(position=0)
    dev2 = build(module, tango, port2)
    dev2.position, dev2.position_known = 0, True
    dev2.set_state(tango.DevState.MOVING)    # as if one were running
    try:
        dev2.queue_move(10)
        check("refused", False, True)
    except ValueError as exc:
        check("refused", True, True)
        check_true("and says why", "already moving" in str(exc))

    print("\ntoo long a move is refused, with the limit named")
    dev2.set_state(tango.DevState.ON)
    try:
        dev2.queue_move(99999)
        check("refused", False, True)
    except ValueError as exc:
        check("refused", True, True)
        check_true("names MaxStepsPerMove", "20000" in str(exc))
    check("nothing was sent to the board", port2.sent, [])

    print("\nGoToPreset works out the distance from where it is")
    dev2.mover = module.MoveThread(dev2)
    dev2.mover.start()
    dev2.position, dev2.position_known = 250, True
    port2.position = 250
    dev2.do_gotopreset(3)                       # presets are 0,1000,2000,3000
    wait_idle(dev2)
    check("moved the difference to 2000", port2.sent[-1], "+1750")
    check("arrived", dev2.position, 2000)

    print("\nand refuses what it cannot work out")
    for index, why in ((9, "does not exist"), (0, "does not exist")):
        try:
            dev2.do_gotopreset(index)
            check("preset %d refused" % index, False, True)
        except ValueError as exc:
            check_true("preset %d refused: %s" % (index, why), why in str(exc))
    dev2.position_known = False
    try:
        dev2.do_gotopreset(2)
        check("refused with an unknown position", False, True)
    except ValueError as exc:
        check_true("refused with an unknown position",
                   "not known" in str(exc))
    dev2.position_known = True

    print("\nZero goes through the queue like a move")
    dev2.queue_move(0)
    wait_idle(dev2)
    check("sent Z", port2.sent[-1], "Z")
    check("position is zero", dev2.position, 0)

    print("\na board that is something else is not driven")
    other = StubSerial(identity="Motor Sputtering v2")
    dev3 = build(module, tango, other)
    # init_device's identity check, without the Device machinery it needs.
    identity = dev3.exchange("I")
    check_true("the stub answers as the other board",
               identity.startswith("Motor Sputtering"))
    check_true("which does not pass the check",
               not identity.startswith("MotorApertura"))

    print("\nevery exchange carries a deadline")
    # A read with no timeout is how a device server stops answering at all.
    slow = StubSerial()
    dev4 = build(module, tango, slow)
    dev4.exchange("?", extra_wait=12.0)
    check("timeout sized for the move", slow.timeout,
          module.REPLY_MARGIN + 12.0)

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
