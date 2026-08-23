#!/usr/bin/env python3
"""Find Python 2 residue: bytes coming out of a library and meeting str in the code.

On Python 2 these servers could ignore the difference. They cannot now, and the
failure is not always loud: comparing bytes to a str literal is silently False,
so a device reports the wrong state rather than crashing. NetworkUPSTool was
found this way in August 2026 — GetUPSVars returns a dict keyed by bytes, and
indexing it with "ups.status" raised KeyError and killed init_device.

The first attempt at this audit was a pipeline of greps, and it missed that very
case twice over: an exclusion added to cut noise ('status') also matched inside
'ups.status', and there was no pattern for the actual cause, subscripting an
external dict with a str literal. Hence a real tool, with the broken file kept as
a test so the method is checked before it is believed.

WHAT IT LOOKS FOR

Values are tracked from the call that produces them, through assignments and
slices, until something consumes them. It reports where such a value meets a str:

    tainted["literal"]        KeyError        the cause of the NetworkUPSTool bug
    tainted == "literal"      silently False  the dangerous one
    tainted.split("literal")  TypeError
    "...%s" % tainted         prints b'...'   cosmetic

float(), int() and len() are NOT reported: they accept bytes in Python 3.
Verified: float(b"1.5") -> 1.5, int(b"12") -> 12, int(b"00ff", 16) -> 255.

Neither is indexing a single byte: b"abc"[0] is an int, so "%d" % r[0] is
correct. Only a slice stays bytes. Getting that wrong made 8 of the first 14
findings false, all of them in WisselMCA.

WHICH CALLS PRODUCE WHAT

Resolved through the object, not the method name: self.ser.read() and
self.dev.read() are both `read` and return different things. Objects are bound
to a library by their constructor in a first pass over the whole module, because
the assignment lives in init_device and the uses are elsewhere.

Usage:  python3 tools/audit_bytes.py [--root PATH] [--self-test] [file ...]
Exit:   0 nothing found, 1 findings, 2 the self-test failed or it could not run.
"""

import ast
import os
import re
import subprocess
import sys

# ---------------------------------------------------------------- what kinds
BYTES = "bytes"          # a bytes object
INTLIST = "intlist"      # a list of ints, as cython-hidapi returns
INT = "int"              # one element out of either of those
CONTAINER = "container"  # dict or list whose contents are bytes
CLEAN = "clean"
UNKNOWN = "unknown"

# ------------------------------------------------------------ taint table
#
# Library         Returns                       How it was confirmed
# --------------  ----------------------------  ---------------------------
# pyserial        bytes                         source, pyserial 3.5:
#                                               read() ends `return bytes(read)`
#                                               read_until() `return bytes(line)`
# socket          bytes                         recv() documented and checked
# PyNUT           dict/list WITH BYTES INSIDE   measured on pi-leem:
#                                               type(list(v)[0]) is bytes
# hid             list of int                   working code on the MCA does
#                 (cython-hidapi)               r[0]!=130 and bytes(r[2:130])
# RPi.GPIO        int                           measured: GPIO.input(21) -> 1
# w1thermsensor   float                         measured: 28.75
# simple_pid      float                         pure Python, no I/O
# numpy           ndarray                       not a data source here
#
# Only the first four appear here; the rest cannot put bytes into the code.
# Adding a library means adding its constructors and its methods, and because
# lookup goes through the object, a new library with its own read() cannot be
# confused with pyserial's.

LIBRARIES = {
    "serial": {
        "constructors": {"Serial"},
        "methods": {"read": BYTES, "readline": BYTES, "readlines": BYTES,
                    "read_until": BYTES, "read_all": BYTES},
    },
    "socket": {
        "constructors": {"socket"},
        "methods": {"recv": BYTES, "recvfrom": BYTES},
    },
    "hid": {
        "constructors": {"device", "Device"},
        "methods": {"read": INTLIST, "get_feature_report": INTLIST},
    },
    "PyNUT": {
        "constructors": {"PyNUTClient"},
        "methods": {"GetUPSVars": CONTAINER, "GetUPSCommands": CONTAINER,
                    "GetUPSList": CONTAINER, "GetUPSNames": CONTAINER,
                    "GetRWVars": CONTAINER},
    },
}

# Every method name any library produces data with. Used only to notice that a
# call looks like a source but its object could not be resolved, which would
# otherwise be a silent gap in coverage.
ALL_SOURCE_METHODS = {m for lib in LIBRARIES.values() for m in lib["methods"]}

CLEANING_CALLS = {"decode"}
CONSUMING = {"str", "int", "float", "len", "ord", "bool", "sorted", "sum"}

STR_METHODS = {"split", "rsplit", "startswith", "endswith", "find", "rfind",
               "index", "replace", "strip", "lstrip", "rstrip", "join",
               "partition", "count"}

# %s and %r accept anything; the rest need a number, so bytes there raises.
TEXT_SPEC = re.compile(r"%[-+ #0-9.*]*[sr]")


def is_str_const(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def bind_objects(tree):
    """name -> library, from constructor calls anywhere in the module.

    self.ser = serial.Serial(...) sits in init_device while self.ser.readline()
    is called from a read_ method, so this has to be a whole-module pass.
    """
    bound = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        f = node.value.func
        if not isinstance(f, ast.Attribute) or not isinstance(f.value, ast.Name):
            continue
        lib = LIBRARIES.get(f.value.id)
        if lib and f.attr in lib["constructors"]:
            for t in node.targets:
                name = dotted(t) if isinstance(t, (ast.Name, ast.Attribute)) else None
                if name:
                    bound[name] = f.value.id
    # Threads reach the port through the device object, `self.ds.ser`, while
    # the binding was recorded as `self.ser`. Resolve on the last component as
    # well, but only where it is unambiguous across the whole module.
    by_attr = {}
    for name, lib in bound.items():
        leaf = name.rsplit(".", 1)[-1]
        if by_attr.get(leaf, lib) != lib:
            by_attr[leaf] = None           # two libraries, refuse to guess
        else:
            by_attr[leaf] = lib
    for leaf, lib in by_attr.items():
        if lib:
            bound.setdefault("*." + leaf, lib)
    return bound


class Scan(ast.NodeVisitor):
    """One pass over a function body, tracking which names hold what."""

    def __init__(self, server, path, func, objects):
        self.server, self.path, self.func = server, path, func
        self.objects = objects
        self.kind = {}
        self.findings = []

    # -- what is this expression? -------------------------------------------
    def kind_of(self, node):
        if isinstance(node, ast.Call):
            return self._kind_of_call(node)
        if isinstance(node, ast.Constant):
            return BYTES if isinstance(node.value, bytes) else CLEAN
        if isinstance(node, ast.Name):
            return self.kind.get(node.id, UNKNOWN)
        if isinstance(node, ast.Attribute):
            return self.kind.get(dotted(node), UNKNOWN)
        if isinstance(node, ast.Subscript):
            inner = self.kind_of(node.value)
            if inner == CONTAINER:
                return BYTES                     # a value out of the dict
            if inner in (BYTES, INTLIST):
                # b"abc"[0] is an int; only a slice keeps the sequence.
                if isinstance(node.slice, ast.Slice):
                    return inner
                return INT
            return UNKNOWN
        if isinstance(node, ast.BinOp):
            for side in (node.left, node.right):
                if self.kind_of(side) in (BYTES, INTLIST):
                    return BYTES
            return UNKNOWN
        return UNKNOWN

    def _kind_of_call(self, node):
        f = node.func
        if isinstance(f, ast.Name):
            if f.id in CONSUMING:
                return CLEAN
            if f.id == "bytes":
                return BYTES
            return UNKNOWN
        if not isinstance(f, ast.Attribute):
            return UNKNOWN
        if f.attr in CLEANING_CALLS:
            return CLEAN
        target = dotted(f.value)
        lib = self.objects.get(target)
        if lib is None and "." in target:
            lib = self.objects.get("*." + target.rsplit(".", 1)[-1])
        if lib:
            return LIBRARIES[lib]["methods"].get(f.attr, UNKNOWN)
        if f.attr in ALL_SOURCE_METHODS:
            # Looks like a source but the object was never bound to a library.
            # Reported so that a gap in coverage is visible rather than silent.
            self.findings.append({
                "server": self.server,
                "where": "%s:%d" % (self.path, node.lineno),
                "func": self.func,
                "what": "%s() on %s, whose library could not be resolved"
                        % (f.attr, dotted(f.value) or "?"),
                "risk": "not analysed",
            })
        return UNKNOWN

    def target_name(self, node):
        if isinstance(node, (ast.Name, ast.Attribute)):
            return dotted(node)
        return None

    def report(self, node, what, effect, raises):
        # Only something that actually raises can break start-up. A message
        # printing b'...' in init_device is still only a message.
        risk = effect
        if raises and self.func == "init_device":
            risk = "breaks at start-up"
        self.findings.append({"server": self.server,
                              "where": "%s:%d" % (self.path, node.lineno),
                              "func": self.func, "what": what, "risk": risk})

    # -- visits -------------------------------------------------------------
    def visit_Assign(self, node):
        self.generic_visit(node)
        k = self.kind_of(node.value)
        for t in node.targets:
            name = self.target_name(t)
            if name:
                if k in (BYTES, INTLIST, CONTAINER, INT):
                    self.kind[name] = k
                else:
                    self.kind.pop(name, None)

    def visit_Compare(self, node):
        self.generic_visit(node)
        left = self.kind_of(node.left)
        for op, comp in zip(node.ops, node.comparators):
            if not isinstance(op, (ast.Eq, ast.NotEq)):
                continue
            right = self.kind_of(comp)
            sequence = (BYTES, INTLIST, INT)
            if (left in sequence and is_str_const(comp)) or \
               (right in sequence and is_str_const(node.left)):
                self.report(node, "bytes compared against a str literal",
                            "silent: always False", raises=False)

    def visit_Subscript(self, node):
        self.generic_visit(node)
        if self.kind_of(node.value) == CONTAINER and is_str_const(node.slice):
            self.report(node,
                        "container of bytes indexed with the str literal %r"
                        % node.slice.value, "runtime: KeyError", raises=True)

    def visit_Call(self, node):
        self.generic_visit(node)
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in STR_METHODS:
            if self.kind_of(f.value) in (BYTES, INTLIST):
                if any(is_str_const(a) for a in node.args):
                    self.report(node,
                                "bytes.%s() called with a str literal" % f.attr,
                                "runtime: TypeError", raises=True)

    def visit_BinOp(self, node):
        self.generic_visit(node)
        left, right = self.kind_of(node.left), self.kind_of(node.right)
        if isinstance(node.op, ast.Mod) and is_str_const(node.left) \
                and right in (BYTES, INTLIST):
            if TEXT_SPEC.search(node.left.value):
                self.report(node, "bytes formatted into a str with %s",
                            "cosmetic: shows b'...'", raises=False)
            else:
                self.report(node, "bytes formatted with a numeric conversion",
                            "runtime: TypeError", raises=True)
        elif isinstance(node.op, ast.Add) and \
                ((is_str_const(node.left) and right in (BYTES, INTLIST)) or
                 (is_str_const(node.right) and left in (BYTES, INTLIST))):
            self.report(node, "str concatenated with bytes",
                        "runtime: TypeError", raises=True)


def scan_source(source, server, path):
    tree = ast.parse(source)
    objects = bind_objects(tree)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            s = Scan(server, path, node.name, objects)
            for stmt in node.body:
                s.visit(stmt)
            out.extend(s.findings)
    return out


def scan_file(path, server=None):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return scan_source(fh.read(), server or os.path.basename(path), path)


# ------------------------------------------------------------------ fixtures
POSITIVE = '''
class D:
    def init_device(self):
        self.client = PyNUT.PyNUTClient()
        self.ser = serial.Serial("/dev/ttyUSB0")
        self.varsUPS = self.client.GetUPSVars(self.UPSunitName)
        if (self.varsUPS["ups.status"] == "OL"):
            pass
    def read_thing(self):
        resp = self.ser.readline()
        if resp == "READY":
            pass
        parts = resp.split(",")
        self.set_status("got %s" % resp)
        return "x" + resp
'''

# The six real findings of 22-ago-2026, in the shapes they actually have.
# Pinned before the false-positive fix so that fixing the noise cannot quietly
# remove the signal, which is exactly how the grep version failed.
COSMETIC = '''
class D:
    def init_device(self):
        self.ser = serial.Serial("/dev/ttyUSB0")
        b = self.ser.readline()
        self.set_status("Connected to %s" % b)          # ArduinoMotor:90
        self.set_status("IDN? returned %s" % b)         # ArduinoMotor:94
    def write_SetVoltage(self):
        resp = self.ser.readline()
        self.set_status("Error writing %s" % resp[:-1])   # FUGMCP:200
        self.debug_stream("Error writing %s" % resp[:-1]) # FUGMCP:201
'''

# Correct code that the first version wrongly flagged: hid returns a list of
# ints, one element of it is an int, and "%d" on an int is right.
NEGATIVE = '''
class D:
    def _get_vars(self):
        raw = self.client.GetUPSVars(self.UPSunitName)
        return {k.decode(): v.decode() for k, v in raw.items()}
    def init_device(self):
        self.client = PyNUT.PyNUTClient()
        self.dev = hid.device()
        self.ser = serial.Serial("/dev/ttyUSB0")
        self.varsUPS = self._get_vars()
        if (self.varsUPS["ups.status"] == "OL"):
            pass
    def readmode(self):
        r = self.dev.read(4)
        if (r[0] != 3):
            return (False, "wrong count in response %d" % r[0])
        return (True, r[2])
    def read_thing(self):
        resp = self.ser.readline().decode("ascii")
        if resp == "READY":
            pass
        v = float(self.ser.readline())
        n = int(self.ser.read(4), 16)
        if self.ser.read(1) == b"\\x06":
            pass
        return v + n
'''


def self_test(repo):
    ok = True

    found = scan_source(POSITIVE, "fixture", "<positive>")
    if len(found) < 5:
        print("SELF-TEST FAILED: the positive fixture has five distinct "
              "mistakes, %d were found" % len(found))
        for f in found:
            print("    found: %s" % f["what"])
        ok = False
    if not any("indexed with the str literal" in f["what"] for f in found):
        print("SELF-TEST FAILED: the container-indexed-with-str-literal case "
              "is the one that started all this and it was not found")
        ok = False
    if not any(f["risk"] == "breaks at start-up" for f in found):
        print("SELF-TEST FAILED: a KeyError in init_device must be reported as "
              "breaking at start-up")
        ok = False

    cosmetic = scan_source(COSMETIC, "fixture", "<cosmetic>")
    if len(cosmetic) != 4:
        print("SELF-TEST FAILED: the four real cosmetic findings must survive; "
              "%d found" % len(cosmetic))
        ok = False
    if any(f["risk"] == "breaks at start-up" for f in cosmetic):
        print("SELF-TEST FAILED: a message printing b'...' does not break "
              "start-up, even inside init_device")
        ok = False

    clean = scan_source(NEGATIVE, "fixture", "<negative>")
    if clean:
        print("SELF-TEST FAILED: the negative fixture is correct code and "
              "%d findings were reported against it:" % len(clean))
        for f in clean:
            print("    %s  %s" % (f["where"], f["what"]))
        ok = False

    real = "NetworkUPSTool/NetworkUPSTool/NetworkUPSTool.py"
    for rev, expect in (("ef437fb^", True), ("ef437fb", False)):
        try:
            src = subprocess.check_output(["git", "show", "%s:%s" % (rev, real)],
                                          cwd=repo, stderr=subprocess.DEVNULL)
        except Exception:
            print("SELF-TEST skipped for %s: not in this history" % rev)
            continue
        got = scan_source(src.decode(), "NetworkUPSTool", real)
        if bool(got) != expect:
            print("SELF-TEST FAILED: %s should%s have been flagged, %d findings"
                  % (rev, "" if expect else " not", len(got)))
            ok = False
        elif expect and not any(f["risk"] == "breaks at start-up" for f in got):
            print("SELF-TEST FAILED: the known bug in %s must read as breaking "
                  "at start-up" % rev)
            ok = False

    print("self-test: %s" % ("passed" if ok else "FAILED"))
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
        findings.extend(scan_file(os.path.join(repo, path), server))

    print("\n%d servers scanned" % len(targets))
    if not findings:
        print("nothing found")
        return 0
    print()
    for f in sorted(findings, key=lambda f: (f["risk"], f["server"])):
        print("%-16s %-46s %s" % (f["server"], f["where"], f["risk"]))
        print("%-16s   %s  (in %s)" % ("", f["what"], f["func"]))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
