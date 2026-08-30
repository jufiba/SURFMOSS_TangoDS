#!/usr/bin/env python3
"""Regression tests for NetworkUPSTool: starting without upsd, and surviving it.

Two faults, found on 30-Aug-2026 with the device sitting in ON while all four
attributes raised BrokenPipeError and the last real reading was hours old:

  init_device opened the client unguarded, so upsd not being up took the whole
  server down -- an exception escaping init_device makes PyTango exit the
  process, and this is the server you most want still talking when the mains
  is misbehaving;

  PyNUT opens one session and never renews it, so a restart of upsd leaves
  this end holding a socket that answers BrokenPipeError for ever.

A third came out of reading the code: ups.status is a set of flags, not a
word. "OL CHRG" is a healthy UPS recharging after a cut. Compared against
"OL" it reported FAULT -- the server calling itself broken exactly when the
UPS had something to say.

Everything runs against a stub of PyNUT, so no upsd is contacted and the live
device on pi-leem is not touched.

Usage:  python3 tools/test_networkupstool.py [--root PATH]
Exit:   0 all passed, 1 failures, 2 could not run.
"""

import os
import sys
import types

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAILS = 0


def check(what, got, want):
    global FAILS
    if got != want:
        FAILS += 1
        print("  FAIL %-44s got %r want %r" % (what, got, want))
    else:
        print("  ok   %-44s %r" % (what, got))


class Upsd:
    """A stand-in for upsd, with a switch for each way it lets you down."""

    VARS = {
        b"ups.status": b"OL",
        b"ups.temperature": b"34.0",
        b"ups.load": b"20",
        b"battery.charge": b"100",
    }

    def __init__(self):
        self.up = True            # accepts connections
        self.broken = False       # accepts them, then the pipe dies
        self.status = "OL"
        self.drop = set()         # variables this model does not publish
        self.connects = 0
        self.fetches = 0

    def client(self, *args, **kwargs):
        self.connects += 1
        if not self.up:
            raise ConnectionRefusedError("[Errno 111] Connection refused")
        self.broken = False
        return self

    # --- the PyNUT client surface the server uses ---
    def GetUPSVars(self, name):
        self.fetches += 1
        if self.broken:
            raise BrokenPipeError("[Errno 32] Broken pipe")
        out = {k: v for k, v in self.VARS.items() if k not in self.drop}
        out[b"ups.status"] = self.status.encode()
        return out

    def GetUPSCommands(self, name):
        if self.broken:
            raise BrokenPipeError("[Errno 32] Broken pipe")
        return [b"load.off", b"test.battery.start"]


def build(module, tango, upsd):
    class Fake(module.NetworkUPSTool):
        UPSunitName = "LEEM_UPS"

        def __init__(self):
            self.state = tango.DevState.UNKNOWN
            self.status = ""

        def set_state(self, state):
            self.state = state

        def get_state(self):
            return self.state

        def set_status(self, status):
            self.status = status

        def error_stream(self, *a):
            pass

        def warn_stream(self, *a):
            pass

    module.PyNUT.PyNUTClient = upsd.client
    dev = Fake()
    dev.client = None
    dev.varsUPS = {}
    dev.commUPS = []
    dev.lastfetch = 0.0
    dev.lastconnect = 0.0
    return dev


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]

    # A stub PyNUT before the import, so this runs where PyNUT is not
    # installed as well as on the Pi where it is.
    sys.modules.setdefault("PyNUT", types.ModuleType("PyNUT"))
    sys.path.insert(0, os.path.join(repo, "NetworkUPSTool"))
    try:
        import tango
        import importlib
        importlib.import_module("NetworkUPSTool.NetworkUPSTool")
        module = sys.modules["NetworkUPSTool.NetworkUPSTool"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2

    print("\nupsd is not up when the server starts")
    upsd = Upsd()
    upsd.up = False
    dev = build(module, tango, upsd)
    dev._connect()                       # what init_device now calls
    check("state", dev.state, tango.DevState.FAULT)
    check("status says why", "Connection refused" in dev.status, True)
    check("UpsStatus is INVALID", dev.read_UpsStatus()[2],
          tango.AttrQuality.ATTR_INVALID)
    check("Charge is INVALID", dev.read_Charge()[2],
          tango.AttrQuality.ATTR_INVALID)

    print("\nupsd comes up: the retry picks it up, no Init needed")
    upsd.up = True
    dev.lastconnect = 0.0                # RETRY_PERIOD has elapsed
    dev.always_executed_hook()
    check("state", dev.state, tango.DevState.ON)
    check("UpsStatus", dev.read_UpsStatus(), "OnLine")
    check("Charge", dev.read_Charge(), 100.0)

    print("\nupsd is restarted underneath a running server")
    before = upsd.connects
    upsd.broken = True
    dev.lastfetch = 0.0                  # force a fetch rather than the cache
    check("Charge after the pipe broke", dev.read_Charge(), 100.0)
    check("it reconnected exactly once", upsd.connects - before, 1)
    check("state", dev.state, tango.DevState.ON)

    print("\none fetch serves a sweep of the four attributes")
    dev.lastfetch = 0.0
    before = upsd.fetches
    dev.read_UpsStatus(); dev.read_Temperature()
    dev.read_Load(); dev.read_Charge()
    check("fetches for four reads", upsd.fetches - before, 1)

    print("\na variable this model does not publish")
    upsd.drop = {b"ups.temperature"}
    dev.lastfetch = 0.0
    check("Temperature is INVALID", dev.read_Temperature()[2],
          tango.AttrQuality.ATTR_INVALID)
    check("Charge still fine", dev.read_Charge(), 100.0)
    upsd.drop = set()

    print("\nups.status is a set of flags, not a word")
    for flags, state, reported in (
            ("OL", tango.DevState.ON, "OnLine"),
            ("OL CHRG", tango.DevState.ON, "OnLine"),
            ("OB", tango.DevState.STANDBY, "OnBattery"),
            ("OB DISCHRG", tango.DevState.STANDBY, "OnBattery"),
            ("OB LB", tango.DevState.ALARM, "OnBattery"),
            ("ALARM", tango.DevState.ALARM, "ALARM")):
        upsd.status = flags
        dev.lastfetch = 0.0
        got = dev.read_UpsStatus()
        check("%-12s -> %s" % (flags, str(dev.state).rsplit(".", 1)[-1]),
              (dev.state, got), (state, reported))

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
