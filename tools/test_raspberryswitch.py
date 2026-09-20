#!/usr/bin/env python3
"""Regression tests for RaspberrySwitch: State must be current without a
client ever reading the Switch attribute.

Found 20-Sep-2026 wiring leem/vacuum/roughingvalve and leem/power/xps into
AlarmNotifier rules: set_state() lived entirely inside read_Switch(), so
AlarmNotifier -- which only ever calls State() -- saw whatever the last
attribute read (by anyone) happened to leave behind, or just the ON
init_device sets at start-up if nothing had read Switch yet. Fixed by moving
the GPIO read into always_executed_hook(), which Tango calls before every
command or attribute, State() included. See docs/DS-architecture.md and
RaspberrySwitch/README.md.

Runs against a stub of RPi.GPIO, so no real Pi or GPIO pin is touched.

Usage:  python3 tools/test_raspberryswitch.py [--root PATH]
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


class FakeGPIO(types.ModuleType):
    """Just enough of RPi.GPIO: setmode/setup/input, one pin's level under
    the test's control, and a switch to make setup() raise (GPIO busy)."""

    BCM = "BCM"
    IN = "IN"
    PUD_UP = "PUD_UP"
    PUD_DOWN = "PUD_DOWN"

    def __init__(self):
        types.ModuleType.__init__(self, "RPi.GPIO")
        self.level = {}          # pin -> bool
        self.setup_fails = False
        self.input_fails = False

    def setmode(self, mode):
        pass

    def setup(self, pin, direction, pull_up_down=None):
        if self.setup_fails:
            raise RuntimeError("GPIO busy")

    def input(self, pin):
        if self.input_fails:
            raise RuntimeError("no such pin")
        return self.level.get(pin, False)


def build(module, tango, gpio, **props):
    """A RaspberrySwitch with the Device/PyTango machinery stubbed out.

    Mirrors init_device()'s own body rather than calling it: the real
    init_device() opens with Device.init_device(self), which reaches into
    live PyTango server plumbing (ds_class.prop_util) that does not exist
    outside a running server. GPIOport/PullUPorDOWN/Sense are plain class
    attributes here, shadowing the device_property descriptors from the base
    class, exactly as tools/test_analoginterlock.py's Fake does.
    """

    class Fake(module.RaspberrySwitch):
        GPIOport = props.get("GPIOport", 12)
        PullUPorDOWN = props.get("PullUPorDOWN", True)
        Sense = props.get("Sense", True)

        def __init__(self):
            self.state = tango.DevState.UNKNOWN
            self.status = ""
            self._ready = False
            self._switch = False
            try:
                gpio.setmode(gpio.BCM)
                pud = gpio.PUD_UP if self.PullUPorDOWN else gpio.PUD_DOWN
                gpio.setup(self.GPIOport, gpio.IN, pull_up_down=pud)
            except Exception as e:
                self.set_state(tango.DevState.FAULT)
                self.set_status("Can't take GPIO %s: %s" % (self.GPIOport, e))
                return
            self._ready = True
            self.set_state(tango.DevState.ON)

        def set_state(self, state):
            self.state = state

        def get_state(self):
            return self.state

        def set_status(self, status):
            self.status = status

        def error_stream(self, *a):
            pass

    return Fake()


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        repo = args[i + 1]
        del args[i:i + 2]

    gpio = FakeGPIO()
    rpi = types.ModuleType("RPi")
    rpi.GPIO = gpio
    sys.modules["RPi"] = rpi
    sys.modules["RPi.GPIO"] = gpio
    sys.path.insert(0, os.path.join(repo, "RaspberrySwitch"))
    try:
        import tango
        import importlib
        importlib.import_module("RaspberrySwitch.RaspberrySwitch")
        module = sys.modules["RaspberrySwitch.RaspberrySwitch"]
    except ImportError as exc:
        print("cannot import the server (%s); needs PyTango" % exc)
        return 2

    print("\nState follows the pin without ever reading Switch")
    dev = build(module, tango, gpio)
    check("init_device sets ON before any dispatch has run the hook",
          dev.state, tango.DevState.ON)
    gpio.level[12] = False
    dev.always_executed_hook()           # what Tango runs before e.g. State()
    check("first dispatch corrects it from the real (low) pin", dev.state,
          tango.DevState.OFF)
    gpio.level[12] = True
    dev.always_executed_hook()
    check("state follows the pin, no read_Switch() called", dev.state,
          tango.DevState.ON)
    gpio.level[12] = False
    dev.always_executed_hook()
    check("and back", dev.state, tango.DevState.OFF)

    print("\nread_Switch() returns what the hook already computed")
    gpio.level[12] = True
    dev.always_executed_hook()
    check("read_Switch matches the hook's last reading", dev.read_Switch(),
          True)

    print("\nSense=False inverts")
    dev2 = build(module, tango, gpio, Sense=False, GPIOport=4)
    gpio.level[4] = True
    dev2.always_executed_hook()
    check("HIGH with Sense=False -> OFF", dev2.state, tango.DevState.OFF)
    gpio.level[4] = False
    dev2.always_executed_hook()
    check("LOW with Sense=False -> ON", dev2.state, tango.DevState.ON)

    print("\ninit_device failure: FAULT, and the hook leaves the pin alone")
    gpio.setup_fails = True
    dev3 = build(module, tango, gpio, GPIOport=99)
    check("state", dev3.state, tango.DevState.FAULT)
    check("status names the pin", "99" in dev3.status, True)
    gpio.setup_fails = False
    before = dev3.state
    dev3.always_executed_hook()          # must not touch GPIO 99 at all
    check("hook is a no-op once FAULT at start-up", dev3.state, before)

    print("\na read failure in the hook faults cleanly, does not raise")
    dev4 = build(module, tango, gpio, GPIOport=21)
    gpio.input_fails = True
    dev4.always_executed_hook()          # must not raise
    check("state", dev4.state, tango.DevState.FAULT)
    check("status names the pin", "21" in dev4.status, True)
    gpio.input_fails = False

    print("\n%s" % ("FAILURES: %d" % FAILS if FAILS else "all checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
