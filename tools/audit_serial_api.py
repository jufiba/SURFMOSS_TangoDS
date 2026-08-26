#!/usr/bin/env python3
"""Find calls into pyserial that the installed pyserial will not accept.

The Python 2 to 3 work was checked with `python3 -m py_compile` (db0bca9,
"All 40 DS Python files now pass python3 -m py_compile"). A wrong keyword
argument compiles perfectly, so five servers shipped with

    self.ser.read_until(terminator=b"\\r")

`terminator` is the pyserial 2.x name; 3.x calls the argument `expected`. Every
exchange raised TypeError, and from init_device -- where an exception takes the
whole server down -- PfeifferTU400, PfeifferHiscroll and PfeifferTC100 died
seconds after the Starter launched them, with CenterOneGauge and MKSGauge
waiting to do the same at their next restart. Fixed in f018f5b; this is the
check that would have caught it before deployment.

What changed under these servers was not Python but pyserial: the call is
older than the migration and worked on the pyserial 2.x that Python 2 used.
Any library the servers talk to can drift the same way, so the audit is about
the API surface, not about Python versions.

WHAT IT LOOKS FOR

Objects are bound to pyserial by their constructor in a first pass over the
module, because the assignment lives in init_device and the uses are elsewhere
-- the same approach as tools/audit_bytes.py. Then, for every call on such an
object:

    unknown keyword on a known method   TypeError at every call
    unknown keyword to the constructor  ValueError when the port is opened
    a pyserial 2.x camelCase alias      still works, but is deprecated

Both failures are confirmed against pyserial 3.5 on a Pi:
    read_until(terminator=b"x") -> TypeError: ... unexpected keyword argument
    serial_for_url(..., bogus=1) -> ValueError: unexpected keyword arguments

A method that is not in the table is not reported: readline() and friends come
from io at C level and cannot be introspected the same way, and guessing about
them would only produce noise.

THE TABLE

Frozen below from pyserial 3.5, read off the Pi that runs these servers with
inspect.signature. Where pyserial can be imported, --self-test compares the
frozen table against the live one, so it cannot rot unnoticed; off the Pi that
comparison is skipped and the frozen table is used.

Usage:  python3 tools/audit_serial_api.py [--root PATH] [--self-test] [file ...]
Exit:   0 nothing found, 1 findings, 2 the self-test failed or it could not run.
"""

import ast
import os
import subprocess
import sys

# ------------------------------------------------- pyserial 3.5, from the Pi
# method -> the keyword arguments it accepts
METHODS = {
    "apply_settings": {"d"}, "applySettingsDict": {"d"},
    "cancel_read": set(), "cancel_write": set(), "close": set(),
    "fileno": set(), "flush": set(), "flushInput": set(), "flushOutput": set(),
    "getCD": set(), "getCTS": set(), "getDSR": set(), "getRI": set(),
    "getSettingsDict": set(), "get_settings": set(), "inWaiting": set(),
    "iread_until": set(), "isOpen": set(), "nonblocking": set(), "open": set(),
    "read": {"size"}, "read_all": set(), "read_until": {"expected", "size"},
    "readable": set(), "readinto": {"b"},
    "reset_input_buffer": set(), "reset_output_buffer": set(),
    "seekable": set(), "sendBreak": {"duration"}, "send_break": {"duration"},
    "setDTR": {"value"}, "setPort": {"port"}, "setRTS": {"value"},
    "set_input_flow_control": {"enable"}, "set_output_flow_control": {"enable"},
    "writable": set(), "write": {"data"},
}

# Still present in 3.x, so they work; they are the 2.x spellings.
DEPRECATED = {
    "applySettingsDict", "flushInput", "flushOutput", "getCD", "getCTS",
    "getDSR", "getRI", "getSettingsDict", "inWaiting", "isOpen", "sendBreak",
    "setDTR", "setPort", "setRTS",
}

CTOR_KWARGS = {
    "port", "baudrate", "bytesize", "parity", "stopbits", "timeout", "xonxoff",
    "rtscts", "write_timeout", "dsrdtr", "inter_byte_timeout", "exclusive",
}

# Calls that hand back a port object.
CTORS = {"serial.Serial", "serial.serial_for_url", "serial.rs485.RS485"}

FATAL_CALL = "TypeError at every call"
FATAL_OPEN = "ValueError when the port is opened"
STALE = "deprecated in pyserial 3, still works"


def dotted(node):
    """'self.ser' for an Attribute chain, 'ser' for a Name, else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def enclosing_functions(tree):
    """node id -> name of the function it sits in."""
    where = {}
    for func in ast.walk(tree):
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(func):
                where.setdefault(id(node), func.name)
    return where


def port_objects(tree):
    """Names assigned from a pyserial constructor, anywhere in the module."""
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        if dotted(node.value.func) in CTORS:
            for target in node.targets:
                name = dotted(target)
                if name:
                    found.add(name)
    return found


def scan_source(src, server, path):
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [{"server": server, "where": "%s:%s" % (path, exc.lineno),
                 "what": "does not parse: %s" % exc.msg, "func": "?",
                 "risk": FATAL_CALL}]

    ports = port_objects(tree)
    where = enclosing_functions(tree)
    out = []

    def report(node, what, risk):
        func = where.get(id(node), "<module>")
        if func == "init_device" and risk != STALE:
            risk += ", so the server dies at start-up"
        out.append({"server": server, "where": "%s:%d" % (path, node.lineno),
                    "what": what, "func": func, "risk": risk})

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted(node.func)
        if name is None:
            continue

        if name in CTORS:
            for kw in node.keywords:
                if kw.arg is not None and kw.arg not in CTOR_KWARGS:
                    report(node, "%s(%s=...) is not a pyserial argument"
                           % (name, kw.arg), FATAL_OPEN)
            continue

        # a call on a port object: self.ser.read_until(...) -> obj 'self.ser'
        obj, _, method = name.rpartition(".")
        if obj not in ports or method not in METHODS:
            continue
        for kw in node.keywords:
            if kw.arg is not None and kw.arg not in METHODS[method]:
                accepts = ", ".join(sorted(METHODS[method])) or "no keywords"
                report(node, "%s(%s=...) -- %s accepts %s"
                       % (method, kw.arg, method, accepts), FATAL_CALL)
        if method in DEPRECATED:
            report(node, "%s() is the pyserial 2.x spelling" % method, STALE)
    return out


# ------------------------------------------------------------------ fixtures
POSITIVE = '''
import serial
class D:
    def init_device(self):
        self.ser = serial.Serial("/dev/ttyUSB0", 9600, timeout=1)
    def read_one(self):
        return self.ser.read_until(terminator=b"\\r")
    def bad_ctor(self):
        self.ser = serial.Serial("/dev/ttyUSB0", bogus=1)
    def old_spelling(self):
        self.ser.flushInput()
        return self.ser.inWaiting()
'''

NEGATIVE = '''
import serial
class D:
    def init_device(self):
        self.ser = serial.Serial("/dev/ttyUSB0", 9600, timeout=1)
    def read_one(self):
        self.ser.reset_input_buffer()
        return self.ser.read_until(b"\\r")
    def sized(self):
        return self.ser.read_until(expected=b"\\r", size=32)
    def other(self, dev):
        return dev.read_until(terminator=b"\\r")   # not a pyserial object
'''


def live_table():
    """The installed pyserial, if it can be imported here."""
    try:
        import inspect
        import serial
    except ImportError:
        return None, None
    table = {}
    for source in (vars(serial.Serial), vars(serial.SerialBase)):
        for name, obj in source.items():
            if name.startswith("_") or name in table or not inspect.isfunction(obj):
                continue
            try:
                sig = inspect.signature(obj)
            except (TypeError, ValueError):
                continue
            table[name] = {p.name for p in sig.parameters.values()
                           if p.name != "self" and p.kind in
                           (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)}
    return table, getattr(serial, "VERSION", "?")


def self_test(repo):
    ok = True

    found = scan_source(POSITIVE, "fixture", "<positive>")
    if not any("read_until(terminator" in f["what"] for f in found):
        print("SELF-TEST FAILED: the call that started all this, "
              "read_until(terminator=...), was not found")
        ok = False
    if not any(f["risk"].startswith(FATAL_OPEN) for f in found):
        print("SELF-TEST FAILED: an unknown constructor keyword must be reported")
        ok = False
    if not any(f["risk"] == STALE for f in found):
        print("SELF-TEST FAILED: the 2.x camelCase spellings must be reported")
        ok = False
    if not any(f["func"] == "read_one" for f in found):
        print("SELF-TEST FAILED: findings must name the function they are in")
        ok = False
    # A deprecated alias works, so it must never be dressed up as fatal, not
    # even inside init_device -- the same distinction audit_bytes.py draws
    # between a KeyError and a message that merely prints b'...'.
    if any(f["risk"] != STALE and "spelling" in f["what"] for f in found):
        print("SELF-TEST FAILED: a 2.x spelling still works and must not be "
              "reported as breaking anything")
        ok = False

    clean = scan_source(NEGATIVE, "fixture", "<negative>")
    if clean:
        print("SELF-TEST FAILED: the negative fixture is correct code and "
              "%d findings were reported against it:" % len(clean))
        for f in clean:
            print("    %s  %s" % (f["where"], f["what"]))
        ok = False

    # The real regression: five servers, broken before f018f5b and fixed in it.
    real = [
        "PfeifferTU400/PfeifferTU400/PfeifferTU400.py",
        "PfeifferHiscroll/PfeifferHiscroll/PfeifferHiscroll.py",
        "PfeifferTC100/PfeifferTC100/PfeifferTC100.py",
        "CenterOneGauge/CenterOneGauge/CenterOneGauge.py",
        "MKSGauge/MKSGauge/MKSGauge.py",
    ]
    for rev, expect in (("f018f5b^", True), ("f018f5b", False)):
        for path in real:
            try:
                # -c safe.directory: on the Pis the checkout lives on the
                # shared root and is owned by another user, which git refuses
                # to read without this.
                src = subprocess.check_output(
                    ["git", "-c", "safe.directory=%s" % repo, "show",
                     "%s:%s" % (rev, path)], cwd=repo,
                    stderr=subprocess.DEVNULL).decode()
            except Exception:
                print("SELF-TEST skipped for %s: not in this history" % rev)
                break
            hits = [f for f in scan_source(src, os.path.basename(path), path)
                    if "read_until" in f["what"]]
            if bool(hits) != expect:
                print("SELF-TEST FAILED: %s at %s should%s report "
                      "read_until, it did%s"
                      % (path, rev, "" if expect else " not",
                         "" if hits else " not"))
                ok = False

    table, version = live_table()
    if table is None:
        print("note: pyserial is not importable here, so the frozen table "
              "could not be checked against a live one")
    else:
        drift = []
        for name, kwargs in sorted(METHODS.items()):
            if name not in table:
                drift.append("%s is gone from pyserial %s" % (name, version))
            elif table[name] != kwargs:
                drift.append("%s takes %s, the table says %s"
                             % (name, sorted(table[name]) or "no keywords",
                                sorted(kwargs) or "no keywords"))
        if drift:
            print("SELF-TEST FAILED: the frozen table no longer matches the "
                  "installed pyserial %s:" % version)
            for line in drift:
                print("    %s" % line)
            ok = False
        else:
            print("frozen table agrees with the installed pyserial %s" % version)
    return ok


def live_servers(repo):
    import tomllib
    with open(os.path.join(repo, "pyproject.toml"), "rb") as fh:
        conf = tomllib.load(fh)
    out = []
    for pkg, rel in sorted(conf["tool"]["setuptools"]["package-dir"].items()):
        path = os.path.join(rel, pkg + ".py")
        if os.path.isfile(os.path.join(repo, path)):
            out.append((pkg, path))
    return out


DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]
    only_test = "--self-test" in args
    if only_test:
        args.remove("--self-test")

    if not self_test(repo):
        print("\nthe method does not pass its own tests; the result of a run "
              "would mean nothing")
        return 2
    if only_test:
        return 0

    targets = [(os.path.basename(a), a) for a in args] if args \
        else live_servers(repo)

    findings = []
    for server, path in targets:
        full = path if os.path.isabs(path) else os.path.join(repo, path)
        try:
            with open(full, encoding="utf-8") as fh:
                src = fh.read()
        except OSError as exc:
            print("cannot read %s: %s" % (path, exc))
            return 2
        findings.extend(scan_source(src, server, path))

    print("\n%d servers scanned" % len(targets))
    if not findings:
        print("nothing found")
        return 0
    print()
    for f in sorted(findings, key=lambda f: (f["risk"], f["server"])):
        print("%-16s %-52s %s" % (f["server"], f["where"], f["risk"]))
        print("%-16s   %s  (in %s)" % ("", f["what"], f["func"]))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
