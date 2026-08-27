#!/usr/bin/env python3
"""Find the byte framing a Granville Phillips 350 is set to, and prove the cable.

Nothing in the 350's RS-232 protocol reports its own settings: baud rate, byte
size, parity and stop bits are DIP switches on the interface board, and the
only way to learn them from outside is to try. The factory defaults are 300
baud, 7 data bits, no parity, 2 stop bits, and there is no reason to expect a
particular instrument to still be on them.

That is 8 baud rates by 8 framings from the manual's own tables. This walks
them and reports every combination the 350 answers on, so the Baudrate,
Bytesize, Parity and Stopbits properties can be set from evidence rather than
from a guess.

It also answers the other question a first connection raises, which is whether
the null modem cable is wired for this instrument at all:

- Nothing answers on any combination -> no bytes are getting through in at
  least one direction, or the gauge is off.
- SYNTAX ERROR on a message that is not a syntax error -> the bytes arrive but
  DCD is not asserted while they do. The manual gives that as a cause of
  SYNTAX ERROR, and it is a cable question: DCD, CTS and DSR can be forced true
  by switches [22], [23] and [24] on the interface board.
- Unsolicited lines with nothing sent -> switch S1 was off at power-up and the
  module is in talk-only mode, sending all three displays every five seconds.
  A command/response server cannot work against that; S1 has to go on.

Read-only. It sends only DS IG and DGS, which read the pressure and the degas
status. It never sends IG1/IG2 or DG, so it cannot light a filament, and it
cannot start a degas on a gauge someone is using.

Usage:  python3 tools/gp350_probe.py [--self-test] [--root PATH] [port]
        default port: the one on pi-leem this was written for.
Exit:   0 something answered (or the self-test passed), 1 nothing did,
        2 it could not run.
"""

import os
import sys

DEFAULT_PORT = ("/dev/serial/by-path/"
                "platform-3f980000.usb-usb-0:1.1.3:1.0-port0")

# Manual, section 4.2: DIP switches S6-S8.
BAUDS = (9600, 4800, 2400, 1200, 600, 300, 150, 75)

# Manual, section 4.2: DIP switches S3-S5, as (bytesize, parity, stopbits).
FRAMINGS = (
    (8, 'N', 2), (8, 'E', 1), (8, 'O', 1), (7, 'N', 2),
    (7, 'E', 1), (7, 'O', 1), (7, 'E', 2), (7, 'O', 2),
)

ERRORS = ("SYNTAX ERROR", "OVERRUN ERROR", "PARITY ERROR")


def plausible(reply):
    """What this reply says about the settings just tried.

    ('ok', why) a real answer, ('cable', why) bytes arrive but something else
    is wrong, or None if it is noise.
    """
    if not reply:
        return None
    text = reply.strip()
    if text in ERRORS:
        # The 350 understood enough to complain, so the framing is right.
        return ("cable", "answered %s -- the framing is right and the bytes "
                         "arrive, but the message did not parse. On a message "
                         "this simple that points at DCD not being asserted; "
                         "see switches [22]/[23]/[24]." % text)
    if text in ("0", "1"):
        return ("ok", "DGS answered %s" % text)
    try:
        value = float(text)
    except ValueError:
        return None
    if value >= 1.0e9:
        return ("ok", "%s, the gauge-off marker -- the link works and no "
                      "filament is on" % text)
    if 1e-12 <= value <= 1e3:
        return ("ok", "%s, a pressure" % text)
    return None


def listen(ser, seconds):
    """Whatever arrives with nothing sent, for talk-only detection."""
    import time
    end = time.time() + seconds
    got = b""
    old = ser.timeout
    ser.timeout = 0.5
    while time.time() < end:
        chunk = ser.read(256)
        if chunk:
            got += chunk
    ser.timeout = old
    return got.decode("ascii", "replace").strip()


def probe(port):
    import serial
    print("port: %s\n" % port)

    # Talk-only first: it would make every framing below look like it answered.
    try:
        ser = serial.Serial(port, 9600, timeout=1)
    except serial.SerialException as exc:
        print("cannot open the port: %s" % exc)
        return 2
    heard = listen(ser, 6.0)
    ser.close()
    if heard:
        print("unsolicited traffic with nothing sent, at 9600 8N1:\n"
              "   %r\n"
              "   If that repeats about every five seconds the module is in\n"
              "   talk-only mode (switch S1 off at power-up) and no\n"
              "   command/response server can work against it.\n" % heard[:120])
    else:
        print("no unsolicited traffic in 6 s: not in talk-only mode, or\n"
              "   nothing is getting through yet.\n")

    found = []
    for baud in BAUDS:
        for (bits, parity, stop) in FRAMINGS:
            label = "%5d %d%s%d" % (baud, bits, parity, stop)
            try:
                ser = serial.Serial(port, baud, bytesize=bits, parity=parity,
                                    stopbits=stop, timeout=2.0)
            except (serial.SerialException, ValueError) as exc:
                print("   %s  cannot open: %s" % (label, exc))
                continue
            verdict = None
            for message in ("DS IG", "DGS"):
                ser.reset_input_buffer()
                ser.write((message + "\r\n").encode("ascii"))
                reply = ser.read_until(b"\n").decode("ascii", "replace").strip()
                verdict = plausible(reply)
                if verdict:
                    kind, why = verdict
                    print("   %s  %-6s %s -> %s" % (label, kind.upper(),
                                                    message, why))
                    found.append((baud, bits, parity, stop, kind))
                    break
            ser.close()
            if verdict and verdict[0] == "ok":
                break                      # this baud is right; next baud adds nothing
    print()
    if not found:
        print("nothing answered on any of the %d combinations."
              % (len(BAUDS) * len(FRAMINGS)))
        print("Either no bytes are getting through -- check the null modem "
              "cable and that\nthe 350 is powered -- or the gauge is off in a "
              "way that stops even DGS\nanswering, which would be unusual: DGS "
              "answers 0 with no filament on.")
        return 1
    good = [f for f in found if f[4] == "ok"]
    if good:
        (baud, bits, parity, stop, _) = good[0]
        print("Set the device properties to:")
        print("   Baudrate=%d  Bytesize=%d  Parity=%s  Stopbits=%d"
              % (baud, bits, parity, stop))
    else:
        print("The framing was found but every answer was an error reply; see "
              "the note\nabout DCD above.")
    return 0


# ------------------------------------------------------------- the self-test
class StubPort:
    """A port that answers one canned line."""

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


def self_test(repo):
    ok = True

    cases = [
        ("a pressure", "1.20E-07\r\n", "ok"),
        ("the gauge-off marker", "9.90E+09\r\n", "ok"),
        ("degas off", "0\r\n", "ok"),
        ("a syntax error", "SYNTAX ERROR\r\n", "cable"),
        ("nothing", "", None),
        ("line noise", "\x00\xff?\r\n", None),
    ]
    for label, reply, expect in cases:
        got = plausible(reply)
        kind = got[0] if got else None
        if kind != expect:
            print("SELF-TEST FAILED: %s should read as %s, read as %s"
                  % (label, expect, kind))
            ok = False

    if len(BAUDS) != 8 or len(FRAMINGS) != 8:
        print("SELF-TEST FAILED: the manual's tables have 8 baud rates and 8 "
              "framings; this has %d and %d" % (len(BAUDS), len(FRAMINGS)))
        ok = False
    if (7, 'N', 2) not in FRAMINGS or 300 not in BAUDS:
        print("SELF-TEST FAILED: the factory default (300 baud, 7N2) must be "
              "among the combinations tried")
        ok = False

    # The framing of a request, against the server that will send it for real.
    # The outer directory, so that "GranvillePhillips350" is the inner
    # package and not the module inside it. Appended rather than inserted:
    # putting the inner directory first makes the name resolve to the module
    # and the import then fails with "is not a package".
    outer = os.path.join(repo, "GranvillePhillips350")
    for path in (outer, repo):
        if path not in sys.path:
            sys.path.append(path)
    try:
        module = __import__("GranvillePhillips350.GranvillePhillips350",
                            fromlist=["GranvillePhillips350"])
    except ImportError as exc:
        print("note: %s, so the server's own _ask was not exercised. It needs "
              "tango and pyserial, so that part runs on a Pi." % exc)
        return ok

    cls = module.GranvillePhillips350
    device = type("Bound", (), {"_ask": cls._ask, "_pressure": cls._pressure})()
    device.ser = StubPort("1.20E-07\r\n")
    if device._pressure("DS IG") != 1.2e-07:
        print("SELF-TEST FAILED: the server does not read a plain pressure")
        ok = False
    if device.ser.written != b"DS IG\r\n":
        print("SELF-TEST FAILED: the server put %r on the wire"
              % device.ser.written)
        ok = False
    if not device.ser.flushed:
        print("SELF-TEST FAILED: the server does not clear the input buffer "
              "before writing, which talk-only mode makes necessary")
        ok = False

    device = type("Bound", (), {"_ask": cls._ask, "_pressure": cls._pressure})()
    device.ser = StubPort("9.90E+09\r\n")
    if device._pressure("DS IG") is not None:
        print("SELF-TEST FAILED: the gauge-off marker must not be a reading")
        ok = False

    for reply in ERRORS + ("", "nonsense"):
        device = type("Bound", (), {"_ask": cls._ask,
                                    "_pressure": cls._pressure})()
        device.ser = StubPort(reply + "\r\n" if reply else "")
        try:
            device._pressure("DS IG")
            print("SELF-TEST FAILED: %r was accepted as a reading" % reply)
            ok = False
        except module.GP350Error:
            pass

    if ok:
        print("the 350's framing table and the server's own parsing check out")
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
        return 0 if self_test(repo) else 2

    try:
        import serial                                     # noqa: F401
    except ImportError:
        print("pyserial is not installed here; this tool opens a real port "
              "and belongs on the Pi.")
        return 2
    return probe(args[0] if args else DEFAULT_PORT)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
