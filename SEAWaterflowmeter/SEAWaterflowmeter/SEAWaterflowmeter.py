# -*- coding: utf-8 -*-
#
# This file is part of the SEAWaterflowmeter project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" SeaWaterflowmeter

Device server to interface a Raspberry PI using the GPIO to the SEA YF-S201 water flow sensor.
"""

# PyTango imports
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import device_property
from tango import AttrQuality, DispLevel, DevState
from tango import AttrWriteType
# Additional import
# PROTECTED REGION ID(SEAWaterflowmeter.additionnal_import) ENABLED START #
import os
import sys
import time
import atexit
import shutil
import tempfile
import threading

# rpi-lgpio pulls in lgpio, which on import drops a notification FIFO into the
# working directory. On the netbooted Pis that directory is the read-only NFS
# root, so the import dies with FileNotFoundError on '.lgd-nfy-3' -- where -3 is
# not a handle but the error code from failing to create the pipe. The name is
# per-process, not per-server, so two GPIO servers sharing a directory would
# also share the FIFO: give each process its own. Harmless where the original
# RPi.GPIO is installed, which never reads LG_WD.
os.environ.setdefault("LG_WD", tempfile.mkdtemp(prefix="lgpio-"))
atexit.register(shutil.rmtree, os.environ["LG_WD"], True)
import RPi.GPIO as GPIO

from tango import Attr, ArgType, UserDefaultAttrProp

# Number of static channelN attributes kept for backwards compatibility.
MAX_CHANNELS = 4


class ControlThread(threading.Thread):
    """Integrates the pulse counters and publishes the flow rates.

    Differences from the original implementation:

    * counters are monotonic and per-device; the rate is computed from the
      *difference* between two snapshots, so pulses arriving while the
      snapshot is taken are not lost (the old code zeroed a shared global
      dictionary every cycle).
    * the elapsed time is measured, not assumed, so a delayed cycle does not
      report a spuriously high flow.
    * the loop body is guarded: an exception puts the device in FAULT instead
      of silently freezing the last good reading, which is the failure mode
      an interlock reading these attributes cannot detect.
    """

    def __init__(self, ds):
        threading.Thread.__init__(self, name="SEAWaterflowmeter-ctrl")
        self.daemon = True
        self.ds = ds

    def run(self):
        ds = self.ds
        prev = dict(ds.counters)
        prev_t = time.monotonic()
        try:
            while not ds.stop_event.wait(ds.time):
                now = dict(ds.counters)
                now_t = time.monotonic()
                elapsed = now_t - prev_t
                if elapsed <= 0.0:
                    continue
                for idx, pin in enumerate(ds.pins):
                    pulses = now[pin] - prev[pin]
                    ds.channeldata[idx] = pulses / (elapsed * ds.calibration)
                prev = now
                prev_t = now_t
                ds._updates += 1
        except Exception as exc:
            ds.set_state(tango.DevState.FAULT)
            ds.set_status("Measurement thread died: %s" % exc)
            return
        ds.set_state(tango.DevState.OFF)
        ds.set_status("Measurement thread is NOT running")


# PROTECTED REGION END #    //  SEAWaterflowmeter.additionnal_import

__all__ = ["SEAWaterflowmeter", "main"]


class SEAWaterflowmeter(Device):
    """
    Device server to interface a Raspberry PI using the GPIO to the SEA YF-S201 water flow sensor.
    """
    # PROTECTED REGION ID(SEAWaterflowmeter.class_variable) ENABLED START #
    # The helper methods live here because this is the only region inside the
    # class body that POGO emits for this template, and therefore the only one
    # it will preserve when the code is regenerated from the .xmi. Regions
    # invented by hand (protected_methods, dynamic_attributes) are not in the
    # template and would be dropped, taking these methods with them.
    def _configure(self):
        """Parse the properties, claim the GPIO pins, publish named attributes."""
        for token in self.channels.split(","):
            token = token.strip()
            if token:
                self.pins.append(int(token))
        if not self.pins:
            raise ValueError("property 'channels' is empty")
        if len(self.pins) > MAX_CHANNELS:
            raise ValueError("at most %d channels are supported, got %d"
                             % (MAX_CHANNELS, len(self.pins)))
        if len(set(self.pins)) != len(self.pins):
            raise ValueError("property 'channels' repeats a pin: %r" % (self.pins,))

        names = [n.strip() for n in self.channelnames.split(",") if n.strip()]
        while len(names) < len(self.pins):
            names.append("channel%d" % len(names))
        self.listofnames = names[:len(self.pins)]

        self.counters = dict((pin, 0) for pin in self.pins)

        GPIO.setmode(GPIO.BCM)
        for pin in self.pins:
            GPIO.setup(pin, GPIO.IN)
        for pin in self.pins:
            GPIO.add_event_detect(pin, GPIO.RISING, callback=self._pulse)

        # Label the static channelN attributes from channelnames. The label is
        # set in memory only (no device argument to set_properties), so
        # channelnames stays the single source of truth and nothing is written
        # back to the database.
        for idx, name in enumerate(self.listofnames):
            attr = self.get_device_attr().get_attr_by_name("channel%d" % idx)
            props = attr.get_properties()
            props.label = name
            attr.set_properties(props)

        # Publish one dynamic attribute per physical line, named after it, so a
        # client can ask for "xraygun" instead of "channel0". If the channel
        # order is ever changed, such a client faults loudly rather than
        # silently watching the wrong line.
        for idx, name in enumerate(self.listofnames):
            if name.startswith("channel"):
                continue
            props = UserDefaultAttrProp()
            props.set_label(name)
            props.set_unit("l/min")
            props.set_format("%3.1f")
            attr = Attr(name, ArgType.DevDouble, AttrWriteType.READ)
            attr.set_default_properties(props)
            self.add_attribute(attr, r_meth=self.read_named_channel)
            self.nameindex[name] = idx
            self.dynamic_names.append(name)

    def _pulse(self, channel):
        """GPIO rising-edge callback. Runs in RPi.GPIO's own thread."""
        self.counters[channel] += 1

    def _read_indexed(self, idx):
        """Unconfigured channels report INVALID, never 0.0.

        Returning zero for a channel that does not exist is indistinguishable
        from zero flow, which is exactly the wrong thing to hand an interlock.
        """
        if idx >= len(self.pins):
            return (0.0, time.time(), tango.AttrQuality.ATTR_INVALID)
        return self.channeldata[idx]

    def read_named_channel(self, attr):
        idx = self.nameindex[attr.get_name()]
        attr.set_value(self.channeldata[idx])
    # PROTECTED REGION END #    //  SEAWaterflowmeter.class_variable

    # -----------------
    # Device Properties
    # -----------------

    # NOTE: the default used to be "6,13,19,26". That claimed BCM 26 on every
    # instance that did not override it, which collides with any other server
    # driving that pin (RaspberryButton on pi-xps). Set this property
    # explicitly on every device rather than relying on the default.
    channels = device_property(
        dtype='str', default_value="6,13"
    )

    channelnames = device_property(
        dtype='str', default_value="turbo,xraygun"
    )

    calibration = device_property(
        dtype='double', default_value=7.5
    )

    time = device_property(
        dtype='double', default_value=1.0
    )

    # ----------
    # Attributes
    # ----------

    channel0 = attribute(
        dtype='double',
        label="channel0",
        unit="l/min",
        format="%3.1f",
    )

    channel1 = attribute(
        dtype='double',
        label="channel1",
        unit="l/min",
        format="%3.1f",
    )

    channel2 = attribute(
        dtype='double',
        label="channel2",
        unit="l/min",
        format="%3.1f",
    )

    channel3 = attribute(
        dtype='double',
        label="channel3",
        unit="l/min",
        format="%3.1f",
    )

    UpdateCount = attribute(
        dtype='int',
        label="UpdateCount",
        format="%d",
        doc="Increments once per integration cycle. A client that sees this "
            "stop advancing knows the readings are stale, even though the "
            "flow attributes still return their last value.",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(SEAWaterflowmeter.init_device) ENABLED START #
        self.stop_event = threading.Event()
        self.stop_event.set()
        self.ctrlloop = None
        self._updates = 0
        self.dynamic_names = []
        self.nameindex = {}
        self.pins = []
        self.channeldata = [0.0] * MAX_CHANNELS

        try:
            self._configure()
        except Exception as exc:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Configuration failed: %s" % exc)
            return

        self.stop_event.clear()
        self.ctrlloop = ControlThread(self)
        self.ctrlloop.start()
        self.set_state(tango.DevState.ON)
        self.set_status("Measurement thread is running")
        # PROTECTED REGION END #    //  SEAWaterflowmeter.init_device


    def always_executed_hook(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  SEAWaterflowmeter.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.delete_device) ENABLED START #
        self.stop_event.set()
        if self.ctrlloop is not None and self.ctrlloop.is_alive():
            self.ctrlloop.join(timeout=2.0 + self.time)

        for pin in self.pins:
            try:
                GPIO.remove_event_detect(pin)
            except Exception:
                pass

        for name in self.dynamic_names:
            try:
                self.remove_attribute(name)
            except Exception:
                pass
        self.dynamic_names = []

        # Clean up only the pins this device claimed. A bare GPIO.cleanup()
        # releases every pin the *process* has configured, which would drop the
        # pins of sibling devices in the same server.
        if self.pins:
            try:
                GPIO.cleanup(self.pins)
            except Exception:
                pass
        self.pins = []
        # PROTECTED REGION END #    //  SEAWaterflowmeter.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_channel0(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.channel0_read) ENABLED START #
        return self._read_indexed(0)
        # PROTECTED REGION END #    //  SEAWaterflowmeter.channel0_read

    def read_channel1(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.channel1_read) ENABLED START #
        return self._read_indexed(1)
        # PROTECTED REGION END #    //  SEAWaterflowmeter.channel1_read

    def read_channel2(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.channel2_read) ENABLED START #
        return self._read_indexed(2)
        # PROTECTED REGION END #    //  SEAWaterflowmeter.channel2_read

    def read_channel3(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.channel3_read) ENABLED START #
        return self._read_indexed(3)
        # PROTECTED REGION END #    //  SEAWaterflowmeter.channel3_read

    def read_UpdateCount(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.UpdateCount_read) ENABLED START #
        return self._updates
        # PROTECTED REGION END #    //  SEAWaterflowmeter.UpdateCount_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def turnON(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.turnON) ENABLED START #
        if self.ctrlloop is not None and self.ctrlloop.is_alive():
            return
        if not self.pins:
            tango.Except.throw_exception(
                "SEAWaterflowmeter_NotConfigured",
                "No GPIO channels configured; re-Init the device.",
                "SEAWaterflowmeter.turnON")
        self.stop_event.clear()
        self.ctrlloop = ControlThread(self)
        self.ctrlloop.start()
        self.set_state(tango.DevState.ON)
        self.set_status("Measurement thread is running")
        # PROTECTED REGION END #    //  SEAWaterflowmeter.turnON

    @command(
    )
    @DebugIt()
    def turnOFF(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.turnOFF) ENABLED START #
        if self.ctrlloop is None or not self.ctrlloop.is_alive():
            return
        self.stop_event.set()
        self.ctrlloop.join(timeout=2.0 + self.time)
        self.set_state(tango.DevState.OFF)
        self.set_status("Measurement thread is NOT running")
        # PROTECTED REGION END #    //  SEAWaterflowmeter.turnOFF

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(SEAWaterflowmeter.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((SEAWaterflowmeter,), args=args, **kwargs)
    # PROTECTED REGION END #    //  SEAWaterflowmeter.main


if __name__ == '__main__':
    main()
