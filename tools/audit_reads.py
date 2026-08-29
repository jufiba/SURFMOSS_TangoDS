#!/usr/bin/env python3
"""Which attributes read the instrument on every request, and which do not.

An attribute whose read_<Attr> talks to the instrument costs one exchange per
client per read, so the load scales with how many people are looking -- the one
variable the server does not control. Ten clients at 1 Hz are ten exchanges a
second down one serial port, and the Gamma Vacuum QPC, which will not take
commands back to back, saturates at two.

That is not by itself a defect. It is the right shape for an attribute nobody
watches continuously. It becomes a problem when several clients watch the same
value, and the cure is not to rewrite the server: it is to set polled_attr on
the device, so Tango's polling thread reads at a fixed period and clients read
its buffer. Measured on the QPC afterwards: 0.80 s to the hardware, 0.003 s
from the buffer, and constant traffic whatever the number of clients.

See docs/DS-architecture.md for the measured sweep times and the periods they
imply. This tool answers only the first question: which attributes would
benefit.

WHAT IT REPORTS

    live    read_<Attr> reaches the instrument, following the server's own
            helpers one level (sendcommand, _ask, _fields, ...)
    cached  it returns something a background thread put there

A server with a thread is flagged, because a thread that does more than read --
counting edges, regulating, watching -- is a deliberate design and not a
workaround for load.

Usage:  python3 tools/audit_reads.py [--root PATH] [--self-test] [file ...]
Exit:   0 always, unless the self-test fails (2). This is a survey, not a
        verdict: reading live is not an error.
"""

import ast
import os
import sys

HARDWARE = {
    "Serial", "serial_for_url", "socket", "create_connection", "sendall",
    "recv", "send", "write", "read", "read_until", "readline", "readpage",
    "sendcommand", "sendCommand", "_send_command", "_ask", "_fields",
    "_checked", "cmd", "response", "query", "ask", "GetUPSVars",
    "get_temperature", "input", "output", "read_response", "_pressure",
    "_setpoint", "TCPBlockingReceive",
}


def dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def touches_hardware(func, methods, depth=0):
    for sub in ast.walk(func):
        if not isinstance(sub, ast.Call):
            continue
        name = dotted(sub.func)
        if name is None:
            continue
        leaf = name.rsplit(".", 1)[-1]
        if leaf in HARDWARE:
            return True
        if depth < 1 and name.startswith("self.") and leaf in methods:
            if touches_hardware(methods[leaf], methods, depth + 1):
                return True
    return False


def scan_source(src):
    """(live, cached, has_thread) for one server."""
    tree = ast.parse(src)
    methods = {n.name: n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef)}
    live = cached = 0
    for name, node in methods.items():
        if not name.startswith("read_"):
            continue
        if touches_hardware(node, methods):
            live += 1
        else:
            cached += 1
    has_thread = "threading" in src or "Thread(" in src
    return live, cached, has_thread


# ------------------------------------------------------------------ fixtures
LIVE = '''
class D(Device):
    def read_Pressure(self):
        self.ser.write(b"PR1")
        return float(self.ser.readline())

    def read_Speed(self):
        return int(self.sendcommand("001", "00", "309", "=?")[3])
'''

CACHED = '''
import threading
class D(Device):
    def read_Temperature(self):
        return self.temp

    def read_UpdateCount(self):
        return self.count
'''


def self_test(repo):
    ok = True

    live, cached, thread = scan_source(LIVE)
    if (live, cached) != (2, 0):
        print("SELF-TEST FAILED: both reads reach the instrument, one of them "
              "only through a helper; got live=%d cached=%d" % (live, cached))
        ok = False
    if thread:
        print("SELF-TEST FAILED: no thread in that fixture")
        ok = False

    live, cached, thread = scan_source(CACHED)
    if (live, cached) != (0, 2):
        print("SELF-TEST FAILED: returning an attribute of self is a cached "
              "read; got live=%d cached=%d" % (live, cached))
        ok = False
    if not thread:
        print("SELF-TEST FAILED: the thread in that fixture was not noticed")
        ok = False

    # A real one, to check the helper-following on code that ships: the Pfeiffer
    # servers reach the pump only through sendcommand().
    path = os.path.join(repo, "PfeifferTU400/PfeifferTU400/PfeifferTU400.py")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            live, cached, _ = scan_source(handle.read())
        if live == 0:
            print("SELF-TEST FAILED: PfeifferTU400 reads the pump on every "
                  "attribute, through sendcommand(), and none was seen")
            ok = False

    if ok:
        print("the fixtures and PfeifferTU400 both classify as expected")
    return ok


def live_servers(repo):
    import tomllib
    with open(os.path.join(repo, "pyproject.toml"), "rb") as handle:
        conf = tomllib.load(handle)
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

    rows = []
    for server, path in targets:
        full = path if os.path.isabs(path) else os.path.join(repo, path)
        with open(full, encoding="utf-8") as handle:
            live, cached, thread = scan_source(handle.read())
        if live or cached:
            rows.append((server, live, cached, thread))

    print("\n%-24s %5s %7s  %s" % ("server", "live", "cached", "thread"))
    for server, live, cached, thread in sorted(rows, key=lambda r: (-r[1], r[0])):
        print("  %-22s %5d %7d  %s" % (server, live, cached,
                                       "yes" if thread else ""))
    print("\n%d servers; %d attributes read the instrument on every request, "
          "%d return a cached value" % (len(rows), sum(r[1] for r in rows),
                                        sum(r[2] for r in rows)))
    print("Reading live is not an error. Set polled_attr where several clients "
          "watch the same value;\nsee docs/DS-architecture.md for the measured "
          "periods.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
