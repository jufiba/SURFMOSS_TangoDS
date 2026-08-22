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

Values known to be bytes are tracked from the call that produces them, through
assignments and slices, until something consumes them. It reports where such a
value meets a str:

    tainted["literal"]        KeyError        the cause of the NetworkUPSTool bug
    tainted == "literal"      silently False  the dangerous one
    tainted.split("literal")  TypeError
    "..." % tainted           prints b'...'   cosmetic

float(), int() and len() are NOT reported: they accept bytes in Python 3.
Verified: float(b"1.5") -> 1.5, int(b"12") -> 12, int(b"00ff", 16) -> 255.

Usage:  python3 tools/audit_bytes.py [--root PATH] [--self-test] [file ...]
Exit:   0 nothing found, 1 findings, 2 the self-test failed or it could not run.
"""

import ast
import os
import subprocess
import sys

# ---------------------------------------------------------------- taint table
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
# Only the first three can put bytes into the code, so only they are seeded.

BYTES_CALLS = {          # -> a bytes object
    "read", "readline", "readlines", "read_until", "recv", "recvfrom",
}

CONTAINER_CALLS = {      # -> a dict or list whose contents are bytes
    "GetUPSVars", "GetUPSCommands", "GetUPSList", "GetUPSNames",
}

CLEANING_CALLS = {"decode"}                       # bytes -> str
CONSUMING = {"str", "int", "float", "len", "ord", "bool", "list", "sorted"}

STR_METHODS = {"split", "rsplit", "startswith", "endswith", "find", "rfind",
               "index", "replace", "strip", "lstrip", "rstrip", "join",
               "partition", "count"}

BYTES = "bytes"
CONTAINER = "container"
CLEAN = "clean"
UNKNOWN = "unknown"


def is_str_const(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


class Scan(ast.NodeVisitor):
    """One pass over a function body, tracking which names hold bytes."""

    def __init__(self, server, path, func):
        self.server, self.path, self.func = server, path, func
        self.kind = {}                 # name -> BYTES / CONTAINER / CLEAN
        self.findings = []

    # -- what is this expression? -------------------------------------------
    def kind_of(self, node):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute):
                if f.attr in CLEANING_CALLS:
                    return CLEAN
                if f.attr in BYTES_CALLS:
                    return BYTES
                if f.attr in CONTAINER_CALLS:
                    return CONTAINER
            if isinstance(f, ast.Name):
                if f.id in CONSUMING:
                    return CLEAN
                if f.id == "bytes":
                    return BYTES
            return UNKNOWN
        if isinstance(node, ast.Constant):
            return BYTES if isinstance(node.value, bytes) else CLEAN
        if isinstance(node, ast.Name):
            return self.kind.get(node.id, UNKNOWN)
        if isinstance(node, ast.Attribute):
            return self.kind.get(self._dotted(node), UNKNOWN)
        if isinstance(node, ast.Subscript):
            # a slice of bytes is bytes; a single index gives an int, which
            # compares False against a str just as silently.
            inner = self.kind_of(node.value)
            return BYTES if inner in (BYTES, CONTAINER) else UNKNOWN
        if isinstance(node, ast.BinOp):
            for side in (node.left, node.right):
                if self.kind_of(side) == BYTES:
                    return BYTES
            return UNKNOWN
        return UNKNOWN

    @staticmethod
    def _dotted(node):
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts))

    def target_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return self._dotted(node)
        return None

    # -- record -------------------------------------------------------------
    def report(self, node, what, effect):
        breaks_at_start = self.func == "init_device"
        self.findings.append({
            "server": self.server,
            "where": "%s:%d" % (self.path, node.lineno),
            "func": self.func,
            "what": what,
            "risk": "breaks at start-up" if breaks_at_start else effect,
        })

    # -- visits -------------------------------------------------------------
    def visit_Assign(self, node):
        self.generic_visit(node)
        k = self.kind_of(node.value)
        for t in node.targets:
            name = self.target_name(t)
            if name:
                if k in (BYTES, CONTAINER):
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
            if (left == BYTES and is_str_const(comp)) or \
               (right == BYTES and is_str_const(node.left)):
                self.report(node, "bytes compared against a str literal",
                            "silent: always False")

    def visit_Subscript(self, node):
        self.generic_visit(node)
        if self.kind_of(node.value) == CONTAINER and is_str_const(node.slice):
            self.report(node,
                        "container of bytes indexed with the str literal %r"
                        % node.slice.value, "runtime: KeyError")

    def visit_Call(self, node):
        self.generic_visit(node)
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in STR_METHODS:
            if self.kind_of(f.value) == BYTES:
                if any(is_str_const(a) for a in node.args):
                    self.report(node,
                                "bytes.%s() called with a str literal" % f.attr,
                                "runtime: TypeError")

    def visit_BinOp(self, node):
        self.generic_visit(node)
        left, right = self.kind_of(node.left), self.kind_of(node.right)
        if isinstance(node.op, ast.Mod) and is_str_const(node.left) \
                and right == BYTES:
            self.report(node, "bytes formatted into a str with %s",
                        "cosmetic: shows b'...'")
        elif isinstance(node.op, ast.Add) and \
                ((is_str_const(node.left) and right == BYTES) or
                 (is_str_const(node.right) and left == BYTES)):
            self.report(node, "str concatenated with bytes",
                        "runtime: TypeError")


def scan_source(source, server, path):
    """Findings for one module's source text."""
    tree = ast.parse(source)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            s = Scan(server, path, node.name)
            for stmt in node.body:
                s.visit(stmt)
            out.extend(s.findings)
    return out


def scan_file(path, server=None):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return scan_source(fh.read(), server or os.path.basename(path), path)


# ------------------------------------------------------------------ fixtures
#
# Kept inline so the method is checked even if the history is rewritten. The
# git-based check below is the same thing against the real files.

POSITIVE = '''
class D:
    def init_device(self):
        self.client = PyNUT.PyNUTClient()
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

NEGATIVE = '''
class D:
    def _get_vars(self):
        raw = self.client.GetUPSVars(self.UPSunitName)
        return {k.decode(): v.decode() for k, v in raw.items()}
    def init_device(self):
        self.varsUPS = self._get_vars()
        if (self.varsUPS["ups.status"] == "OL"):
            pass
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
    """Check the method before believing it. Loud on failure."""
    ok = True

    found = scan_source(POSITIVE, "fixture", "<positive>")
    kinds = {f["what"].split("(")[0].strip() for f in found}
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
        print("SELF-TEST FAILED: a mistake in init_device must be reported as "
              "breaking at start-up")
        ok = False

    clean = scan_source(NEGATIVE, "fixture", "<negative>")
    if clean:
        print("SELF-TEST FAILED: the negative fixture is correct code and "
              "%d findings were reported against it:" % len(clean))
        for f in clean:
            print("    %s  %s" % (f["where"], f["what"]))
        ok = False

    # Same check against the real thing, before and after the fix.
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
    """The servers in [project.scripts], which is what LIVE means here."""
    import tomllib
    with open(os.path.join(repo, "pyproject.toml"), "rb") as fh:
        conf = tomllib.load(fh)
    pkgdir = conf["tool"]["setuptools"]["package-dir"]
    out = []
    for pkg, rel in sorted(pkgdir.items()):
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

    if args:
        targets = [(os.path.basename(a), a) for a in args]
    else:
        targets = live_servers(repo)

    findings = []
    for server, path in targets:
        findings.extend(scan_file(os.path.join(repo, path), server))

    print("\n%d servers scanned" % len(targets))
    if not findings:
        print("nothing found")
        return 0
    print()
    for f in sorted(findings, key=lambda f: (f["risk"], f["server"])):
        print("%-18s %-52s %s" % (f["server"], f["where"], f["risk"]))
        print("%-18s   %s  (in %s)" % ("", f["what"], f["func"]))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
