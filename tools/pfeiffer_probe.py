#!/usr/bin/env python3
"""Ask every serial port which Pfeiffer pump, if any, is on the other end.

A Pfeiffer device server is told its port by a SerialPort property holding a
/dev/serial/by-path name, and there is nothing in Tango that checks the pump on
the far end is the one meant. Twice in one day that mattered:

- PfeifferTU400/1 and PfeifferHiscroll/1 were looked for on pi-leem, which has
  a USB tree numbered so much like pi-uleem's that both properties named ports
  that existed there. Nothing answered on any of them. Run against pi-uleem the
  probe found 'HiScrl' at address 002 on the very port the property named, and
  the servers had simply been looked for on the wrong Pi.
- The TU400's converter was then reconnected by hand, and the probe is what
  confirmed 'TC 400' had come back at address 001, before any server was
  started.

Read-only. Only action '00' (request) is ever sent, never '10' (set). That
matters: aiming Start, Stop or SetRotSpeed at whatever is actually on a port is
how a vacuum system gets damaged, so identify first and write the property
after.

Answering with a name is also the only way to tell a pump that is switched off
from a property that points at the wrong port -- both are silence.

Stop the device server first. The port is not locked against a second opener:
probing one that a running server is polling was tried and it worked, but both
sides are then writing to the same bus and each can read the other's reply as
its own. Nothing here can detect that.

    --self-test drives the sendcommand() of the three servers over a stub port
    through a good frame and every way a bad one can arrive. The bug that broke
    all three, read_until(terminator=...), was invisible to py_compile, so this
    checks the framing against the real code before any reading is believed.
    tools/audit_serial_api.py is the static half of the same concern.

Usage:  python3 tools/pfeiffer_probe.py [--self-test] [--root PATH] [port ...]
        with no ports, every /dev/serial/by-path entry is tried.
Exit:   0 something answered (or the self-test passed), 1 nothing answered,
        2 it could not run.
"""

import glob
import os
import sys

NAME, FIRMWARE, RUNNING = "349", "312", "010"
BAUDS = (9600, 19200)
ADDRESSES = range(1, 17)
MINFRAME = 14


def crc_code(text):
    return sum(ord(c) for c in text) % 256


def frame(address, action, parameter, data):
    body = "%03d%s%s%02d%s" % (address, action, parameter, len(data), data)
    return body + "%03d" % crc_code(body) + "\r"


def unframe(reply):
    """The data field, or None if this is not a whole, self-consistent frame."""
    if not reply.endswith("\r") or len(reply) < MINFRAME:
        return None
    if not reply[8:10].isdigit():
        return None
    n = int(reply[8:10])
    if len(reply) != n + MINFRAME:
        return None
    if reply[-4:-1] != "%03d" % crc_code(reply[:-4]):
        return None
    return reply[10:10 + n]


def ask(ser, address, parameter):
    ser.reset_input_buffer()
    ser.write(frame(address, "00", parameter, "=?").encode("ascii"))
    return unframe(ser.read_until(b"\r").decode("ascii", "replace"))


def by_id_for(path):
    """The stable by-id name of the same adapter, when it has one."""
    try:
        target = os.path.realpath(path)
    except OSError:
        return None
    for candidate in glob.glob("/dev/serial/by-id/*"):
        if os.path.realpath(candidate) == target:
            return os.path.basename(candidate)
    return None


def probe(ports):
    import serial
    answered = False
    for path in ports:
        stable = by_id_for(path)
        print("\n%s" % path)
        if stable:
            print("   by-id: %s" % stable)
        for baud in BAUDS:
            try:
                ser = serial.Serial(path, baud, bytesize=8, parity="N",
                                    stopbits=1, timeout=0.6)
            except serial.SerialException as exc:
                print("   cannot open: %s" % exc)
                break
            hits = []
            for address in ADDRESSES:
                name = ask(ser, address, NAME)
                if name is None:
                    continue
                hits.append("   %d baud  address %03d  name=%r firmware=%r "
                            "running=%r" % (baud, address, name,
                                            ask(ser, address, FIRMWARE),
                                            ask(ser, address, RUNNING)))
            ser.close()
            if hits:
                print("\n".join(hits))
                answered = True
                break
            print("   %d baud  nothing answered at addresses %03d-%03d"
                  % (baud, ADDRESSES[0], ADDRESSES[-1]))
    return answered


# ------------------------------------------------------------- the self-test
SERVERS = ("PfeifferTU400", "PfeifferHiscroll", "PfeifferTC100")


class StubPort:
    """A port that replies with one canned frame, and records what was sent."""

    def __init__(self, reply):
        self.reply = reply
        self.written = None
        self.flushed = False

    def reset_input_buffer(self):
        self.flushed = True

    def write(self, data):
        self.written = data

    def read_until(self, expected=b"\n", size=None):
        return self.reply.encode("ascii")


def bound(module, name):
    """An object carrying just the framing methods of a server class."""
    cls = getattr(module, name)
    return type("Bound", (), {"crc_code": cls.crc_code,
                              "sendcommand": cls.sendcommand,
                              "MINFRAME": cls.MINFRAME})


def cases():
    good = frame(1, "10", "309", "000820")
    bad_crc = good[:-4] + "%03d" % ((crc_code(good[:-4]) + 1) % 256) + "\r"
    wrong_len = good[:8] + "03" + good[10:]
    yield "a good reply", good, None
    yield "an empty data field", frame(1, "10", "309", ""), None
    yield "nothing at all", "", "no reply"
    yield "no terminator", good[:-1], "no reply"
    yield "a truncated frame", "001103\r", "short reply"
    yield "a length that is not digits", good[:8] + "XX" + good[10:], "no length"
    yield "a length that disagrees", wrong_len, "announces 3 data"
    yield "a bad checksum", bad_crc, "checksum mismatch"
    yield "a reply to another parameter", frame(1, "10", "316", "000820"), \
        "the reply is for 316"


def self_test(repo):
    for path in (repo, os.path.join(repo, "..")):
        if path not in sys.path:
            sys.path.insert(0, path)
    ok = True
    for name in SERVERS:
        sys.path.insert(0, os.path.join(repo, name))
        try:
            module = __import__(name + "." + name, fromlist=[name])
        except ImportError as exc:
            print("SELF-TEST could not run: %s will not import (%s).\n"
                  "It needs tango and pyserial, so it runs on a Pi, not on a "
                  "laptop." % (name, exc))
            return None
        error = getattr(module, "PfeifferError")
        cls = bound(module, name)

        for label, reply, expect in cases():
            device = cls()
            device.ser = StubPort(reply)
            try:
                got = device.sendcommand("001", "00", "309", "=?")
                outcome, good = "returned %r" % (got,), expect is None
            except error as exc:
                outcome, good = str(exc), expect is not None and expect in str(exc)
            except Exception as exc:                      # noqa: BLE001
                outcome = "%s: %s -- not a PfeifferError" % (type(exc).__name__, exc)
                good = False
            if not good:
                print("SELF-TEST FAILED: %s, given %s: %s"
                      % (name, label, outcome))
                ok = False

        # The buffer must be cleared before writing, or the tail of a rejected
        # exchange is read as the next reply.
        device = cls()
        device.ser = StubPort(frame(1, "10", "309", "000820"))
        device.sendcommand("001", "00", "309", "=?")
        if not device.ser.flushed:
            print("SELF-TEST FAILED: %s does not clear the input buffer "
                  "before writing" % name)
            ok = False
        sent = device.ser.written.decode("ascii")
        if sent != frame(1, "00", "309", "=?"):
            print("SELF-TEST FAILED: %s put %r on the wire" % (name, sent))
            ok = False
    if ok:
        print("the framing of %s checks out against %d replies each"
              % (", ".join(SERVERS), len(list(cases())) + 1))
    return ok


DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]
    if "--self-test" in args:
        args.remove("--self-test")
        result = self_test(repo)
        return 2 if result is None else (0 if result else 2)

    try:
        import serial                                     # noqa: F401
    except ImportError:
        print("pyserial is not installed here; this tool opens real ports and "
              "belongs on a Pi.")
        return 2

    print("Stop the device servers using these ports first: the port is not "
          "locked, and\ntwo openers on one bus read each other's replies.\n")
    ports = args or sorted(p for p in glob.glob("/dev/serial/by-path/*")
                           if "usbv2" not in p)
    if not ports:
        print("no serial ports found under /dev/serial/by-path")
        return 2
    if not probe(ports):
        print("\nnothing answered on any port. Either no pump is powered, or "
              "none is cabled to this machine -- the probe cannot tell those "
              "apart, and neither can a device server.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
