#!/usr/bin/env python3
"""Find init_device methods that can take their whole server down with them.

An exception escaping init_device does not fail one device: PyTango exits the
process. The Starter then marks the server FAULT and leaves it there until
somebody restarts it by hand. So a device server for an instrument that is
switched off disappears instead of reporting that it cannot reach it -- which
is how the sputtering rig was found, in August 2026, with seven of its eight
servers gone whenever the rig was off.

Seventeen of the 35 live servers had this. Sixteen were fixed in four batches;
see docs/DS-architecture.md for what each one turned out to need, because
guarding init_device was the smallest part of the work every time.

WHAT IT LOOKS FOR

Calls inside init_device that reach hardware or the network, and that are not
inside a try. Objects are followed one level into the server's own methods, so
a bare self._connect() is judged by what _connect() does -- without that,
GammaVacuumDigitel and WisselMCA read as broken when they are not.

    serial.Serial(), socket.socket(), DeviceProxy(), GPIO.setup(), ...
    self.<method>()   resolved one level, then judged on its contents

⚠️ WHAT IT CANNOT SEE, and why the count is a floor and not a ceiling:

  - Any other exception kills the server just as dead. AnalogInterlock counts
    as clean here and raises explicitly when its thresholds are inconsistent.
  - A device property declared mandatory=True is fetched by
    Device.init_device() itself, before a line of this code runs, and a missing
    one raises there. No guard written in a server can catch that.
  - Silence read as success is not reported at all and is worse than dying:
    ArduinoPt announced ON with nothing connected, because readline() returns
    an empty line on timeout and raises nothing.

Usage:  python3 tools/audit_init_device.py [--root PATH] [--self-test] [file ...]
Exit:   0 nothing found, 1 findings, 2 the self-test failed or it could not run.
"""

import ast
import os
import subprocess
import sys

# Calls that reach hardware or the network, and can therefore raise.
RISKY_FULL = {
    "serial.Serial", "serial.serial_for_url", "socket.socket",
    "socket.create_connection", "tango.DeviceProxy", "DeviceProxy",
    "PyNUT.PyNUTClient", "hid.device", "W1ThermSensor",
    "usbtmc.Instrument", "Gpib.Gpib",
}
RISKY_LEAF = {
    "connect", "open", "write", "read", "readline", "recv", "sendall", "send",
    "setup", "setmode", "add_event_detect", "sendcommand", "_send_command",
    "_ask", "_fields", "_checked", "cmd", "response",
}


def dotted(node):
    """'self.ser.write' for an Attribute chain, 'open' for a Name, else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def guarded_lines(func):
    """Line numbers sitting inside the body of a try within this function."""
    covered = set()
    for sub in ast.walk(func):
        if isinstance(sub, ast.Try):
            for stmt in sub.body:
                for node in ast.walk(stmt):
                    if hasattr(node, "lineno"):
                        covered.add(node.lineno)
    return covered


def unguarded(func, methods, depth=0):
    """Risky calls in func that no try covers, following our own methods once."""
    covered = guarded_lines(func)
    out = []
    for sub in ast.walk(func):
        if not isinstance(sub, ast.Call):
            continue
        name = dotted(sub.func)
        if name is None or sub.lineno in covered:
            continue
        leaf = name.rsplit(".", 1)[-1]
        if name not in RISKY_FULL and leaf not in RISKY_LEAF:
            continue
        if depth < 2 and name.startswith("self.") and leaf in methods:
            # What matters is whether the risk is handled somewhere, not
            # whether init_device itself holds the try.
            out.extend(unguarded(methods[leaf], methods, depth + 1))
            continue
        out.append((leaf, sub.lineno))
    return out


def scan_source(src, server):
    """[] if init_device cannot take the server down, findings otherwise."""
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [("does not parse: %s" % exc.msg, exc.lineno or 0)]
    methods = {n.name: n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef)}
    init = methods.get("init_device")
    if init is None:
        return []
    return unguarded(init, methods)


# ------------------------------------------------------------------ fixtures
VULNERABLE = '''
import serial
class D(Device):
    def init_device(self):
        Device.init_device(self)
        self.ser = serial.Serial(self.SerialPort, 9600)
        self.ser.write(b"?")
'''

GUARDED = '''
import serial
class D(Device):
    def init_device(self):
        Device.init_device(self)
        self.ser = None
        try:
            self.ser = serial.Serial(self.SerialPort, 9600)
        except serial.SerialException as e:
            self.set_state(DevState.FAULT)
            self.set_status("Can't open: %s" % e)
            return
        self.set_state(DevState.ON)
'''

INDIRECT = '''
import socket
class D(Device):
    def init_device(self):
        Device.init_device(self)
        self._connect()

    def _connect(self):
        try:
            self.s = socket.socket()
            self.s.connect((self.IP, self.Port))
        except OSError as e:
            self.set_state(DevState.FAULT)
'''


def self_test(repo):
    ok = True

    if not scan_source(VULNERABLE, "fixture"):
        print("SELF-TEST FAILED: an unguarded serial.Serial() in init_device is "
              "the whole point, and it was not reported")
        ok = False
    if scan_source(GUARDED, "fixture"):
        print("SELF-TEST FAILED: a guarded open was reported")
        ok = False
    if scan_source(INDIRECT, "fixture"):
        print("SELF-TEST FAILED: init_device calling self._connect(), which "
              "guards itself, must not be reported. Without following our own "
              "methods one level, GammaVacuumDigitel and WisselMCA read as "
              "broken when they are not.")
        ok = False

    # The real regression: HuttingerPFGDC before and after the sputtering batch.
    real = "HuttingerPFGDC/HuttingerPFGDC/HuttingerPFGDC.py"
    for rev, expect in (("caa0b20^", True), ("caa0b20", False)):
        try:
            src = subprocess.check_output(
                ["git", "-c", "safe.directory=%s" % repo, "show",
                 "%s:%s" % (rev, real)], cwd=repo,
                stderr=subprocess.DEVNULL).decode()
        except Exception:
            print("SELF-TEST skipped for %s: not in this history" % rev)
            continue
        if bool(scan_source(src, "HuttingerPFGDC")) != expect:
            print("SELF-TEST FAILED: HuttingerPFGDC at %s should%s report, and "
                  "did%s" % (rev, "" if expect else " not",
                             "" if not expect else " not"))
            ok = False

    if ok:
        print("the fixtures and the real before/after both check out")
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

    findings = []
    for server, path in targets:
        full = path if os.path.isabs(path) else os.path.join(repo, path)
        with open(full, encoding="utf-8") as handle:
            for what, line in scan_source(handle.read(), server):
                findings.append((server, path, what, line))

    print("\n%d servers scanned" % len(targets))
    if not findings:
        print("nothing found: no init_device reaches hardware outside a try")
        return 0
    print("\nThese take the whole server down when the instrument is not there:")
    for server, path, what, line in sorted(findings):
        print("   %-22s %s:%d  %s()" % (server, path, line, what))
    print("\nSee docs/DS-architecture.md for the pattern to follow.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
