#!/usr/bin/env python3
"""Regression tests for AlarmNotifier's ctx= handling.

read_context() split every ctx= entry with rpartition("/"), which assumes
every entry is domain/family/member/attribute. Eight of the ten live rules
name the watched device itself instead -- three fields -- so that form was
read as leem/safety + interlockP2lens and every mail from those rules carried

    leem/safety/interlockP2lens = <no se pudo leer: DevFailed[
       desc = Wrong device name syntax (domain/family/member) in leem/safety

where the context should have been. Found 14-Sep-2026 in a real alarm mail
about leem/safety/interlockP2lens: the context is worth least exactly when it
is needed most.

Both shapes are now supported, and a ctx= that is neither is refused when the
rule is parsed rather than when the mail goes out.

Runs against a stub DeviceProxy. No device is contacted.

Usage:  python3 tools/test_alarmnotifier.py [--root PATH]
Exit:   0 all passed, 1 failures, 2 could not run.
"""

import os
import sys

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAILS = 0


def check(what, got, want):
    global FAILS
    if got != want:
        FAILS += 1
        print("  FAIL %-50s got %r want %r" % (what, got, want))
    else:
        print("  ok   %-50s %r" % (what, got))


class StubProxy:
    """Enough of DeviceProxy for read_context, recording what it was built
    with so the test can prove the name was split correctly."""

    built = []

    def __init__(self, name):
        StubProxy.built.append(name)
        self.name = name
        if name.count("/") != 2:
            raise ValueError("Wrong device name syntax "
                             "(domain/family/member) in %s" % name)

    def set_timeout_millis(self, ms):
        pass

    def state(self):
        return "FAULT"

    def status(self):
        return "Can't connect to LEEM2000\nsecond line"

    def read_attribute(self, attr):
        import tango
        r = type("R", (), {})()
        r.quality = tango.AttrQuality.ATTR_VALID
        r.value = "valor-de-%s" % attr
        return r


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]

    sys.path.insert(0, os.path.join(repo, "AlarmNotifier"))
    try:
        import tango
        import importlib
        importlib.import_module("AlarmNotifier.AlarmNotifier")
        module = sys.modules["AlarmNotifier.AlarmNotifier"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2
    Rule = module.Rule

    class Fake(module.AlarmNotifier):
        ProxyTimeout = 500

        def __init__(self):
            pass

    dev = Fake()
    real_proxy = module.tango.DeviceProxy
    module.tango.DeviceProxy = StubProxy
    try:
        print("\nctx= con un device (3 campos): State y Status")
        StubProxy.built = []
        out = dev.read_context("leem/safety/interlockP2lens")
        check("no se parte el nombre", StubProxy.built,
              ["leem/safety/interlockP2lens"])
        check("devuelve State y Status", out,
              "FAULT | Can't connect to LEEM2000 second line")
        check("ya no dice 'Wrong device name syntax'",
              "Wrong device name syntax" in out, False)

        print("\nctx= con un atributo (4 campos): su valor")
        StubProxy.built = []
        out = dev.read_context("leem/safety/interlockP2lens/LastTripReason")
        check("se parte por la ultima barra", StubProxy.built,
              ["leem/safety/interlockP2lens"])
        check("devuelve el valor", out, "valor-de-LastTripReason")

        print("\nctx= con cualquier otra forma: lo dice, no revienta")
        for bad in ("leem/safety", "a/b/c/d/e", "sinbarras"):
            out = dev.read_context(bad)
            check("%-14r -> explicado" % bad,
                  out.startswith("<") and "no es ni un device" in out, True)
    finally:
        module.tango.DeviceProxy = real_proxy

    print("\nuna regla con ctx= mal escrito se rechaza al cargarla")
    base = "name=r dev=a/b/c msg=x"
    ok3 = Rule("name=r dev=a/b/c ctx=leem/safety/interlockP2lens msg=x")
    check("3 campos se acepta", ok3.ctx, ["leem/safety/interlockP2lens"])
    ok4 = Rule("name=r dev=a/b/c ctx=leem/safety/i/LastTripReason msg=x")
    check("4 campos se acepta", ok4.ctx, ["leem/safety/i/LastTripReason"])
    for bad in ("leem/safety", "a/b/c/d/e", "sinbarras"):
        try:
            Rule("name=r dev=a/b/c ctx=%s msg=x" % bad)
            check("ctx=%-12s rechazado" % bad, "aceptado", "ValueError")
        except ValueError as e:
            check("ctx=%-12s rechazado" % bad, "ctx=" in str(e), True)
    ok2 = Rule("name=r dev=a/b/c ctx=a/b/c,d/e/f/g msg=x")
    check("lista mixta se acepta", ok2.ctx, ["a/b/c", "d/e/f/g"])

    print("\nlas diez reglas vivas pasan la validacion")
    try:
        import tango as _t
        rules = list(_t.Database().get_device_property(
            "lab/alarm/notifier", ["Rules"])["Rules"])
        bad = []
        for line in rules:
            try:
                Rule(line)
            except ValueError as e:
                bad.append((line.split()[0], str(e)))
        check("reglas que ahora se rechazarian", bad, [])
    except Exception as e:
        print("  (sin base de datos aqui: %s)" % str(e).split("\n")[0][:50])

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
