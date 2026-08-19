# -*- coding: utf-8 -*-
#
# This file is part of the AnalogInterlock project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" AnalogInterlock

Generic threshold interlock between two Tango devices: reads a numeric
attribute from an input device and asserts or de-asserts a permissive on an
output device.

This is a *secondary* protection layer. It runs in userspace, over CORBA,
between two processes on a Raspberry Pi. Anything that genuinely must not
happen belongs in a hardware chain — a flow switch in series with the supply
enable — not here.

Failure modes and what this server does about each:

  input below threshold      -> de-assert, ALARM
  input attribute unreadable  -> de-assert after MaxReadFailures, FAULT
  input attribute INVALID     -> counted as a read failure
  input publisher frozen      -> de-assert after StaleCycles, ALARM
                                 (detected via HeartbeatAttribute; a frozen
                                 publisher keeps returning its last good value,
                                 which is otherwise indistinguishable from a
                                 healthy reading)
  this server dies            -> keepalives stop; the output device's own
                                 deadman de-asserts. Not handled here, by
                                 construction: a process cannot be its own
                                 watchdog.
  output device unreachable   -> FAULT; nothing else is possible from here
"""

# PyTango imports
import PyTango
from PyTango import DebugIt
from PyTango.server import run
from PyTango.server import Device, DeviceMeta
from PyTango.server import attribute, command
from PyTango.server import device_property
from PyTango import AttrQuality, DispLevel, DevState
from PyTango import AttrWriteType, PipeWriteType
# Additional import
# PROTECTED REGION ID(AnalogInterlock.additionnal_import) ENABLED START #
import os
import sys
import time
import threading


class ControlThread(threading.Thread):
    """Polls the input and maintains the permissive."""

    def __init__(self, ds):
        threading.Thread.__init__(self, name="AnalogInterlock-ctrl")
        self.daemon = True
        self.ds = ds

    def run(self):
        ds = self.ds
        try:
            while not ds.stop_event.wait(ds.PollPeriod):
                try:
                    ds.cycle()
                except Exception as exc:
                    # A cycle must never kill the loop; the loop stopping is
                    # itself the dangerous condition.
                    ds.trip("internal error: %s" % exc, PyTango.DevState.FAULT)
        except Exception as exc:
            ds.trip("control thread died: %s" % exc, PyTango.DevState.FAULT)


# PROTECTED REGION END #    //  AnalogInterlock.additionnal_import

__all__ = ["AnalogInterlock", "main"]


class AnalogInterlock(Device, metaclass=DeviceMeta):
    """
    Generic threshold interlock between two Tango devices.
    """
    # PROTECTED REGION ID(AnalogInterlock.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  AnalogInterlock.class_variable

    # -----------------
    # Device Properties
    # -----------------

    InputDevice = device_property(
        dtype='str',
        doc="Device to read the measured quantity from, e.g. xps/safety/water",
    )

    InputAttribute = device_property(
        dtype='str', default_value="channel0",
        doc="Attribute to read. Prefer a named attribute (e.g. 'xraygun') "
            "over a positional one (e.g. 'channel0'): if the channel order is "
            "ever changed, a named attribute disappears and this server "
            "faults, whereas a positional one silently starts watching a "
            "different line.",
    )

    HeartbeatAttribute = device_property(
        dtype='str', default_value="UpdateCount",
        doc="Monotonic counter on the input device that advances once per "
            "acquisition cycle. Empty string disables staleness detection.",
    )

    OutputDevice = device_property(
        dtype='str',
        doc="Device holding the permissive, e.g. xps/safety/xrayguninterlock",
    )

    OnCommand = device_property(dtype='str', default_value="On")
    OffCommand = device_property(dtype='str', default_value="Off")

    KeepaliveCommand = device_property(
        dtype='str', default_value="Keepalive",
        doc="Sent on every cycle while the permissive is granted. Empty "
            "string disables keepalives, e.g. if the output device does not "
            "implement a deadman.",
    )

    ThresholdOn = device_property(
        dtype='double', default_value=2.0,
        doc="The permissive is granted when the input rises above this.",
    )

    ThresholdOff = device_property(
        dtype='double', default_value=1.6,
        doc="The permissive is withdrawn when the input falls below this. "
            "Must be lower than ThresholdOn; the gap is the hysteresis that "
            "stops the relay chattering around the trip point.",
    )

    PollPeriod = device_property(
        dtype='double', default_value=1.0,
        doc="Seconds between cycles. No point polling faster than the input "
            "device's own integration period.",
    )

    MaxReadFailures = device_property(
        dtype='int', default_value=3,
        doc="Consecutive failed or INVALID reads tolerated before tripping. "
            "Absorbs transient CORBA timeouts without leaving the output "
            "asserted through a real outage.",
    )

    StaleCycles = device_property(
        dtype='int', default_value=5,
        doc="Cycles the heartbeat may fail to advance before tripping.",
    )

    Latching = device_property(
        dtype='bool', default_value=False,
        doc="If True, a trip must be cleared with the Reset command before "
            "the permissive can be granted again. Leave False where the "
            "hardware already latches and requires a physical reset button.",
    )

    ReassertCycles = device_property(
        dtype='int', default_value=30,
        doc="Re-send OnCommand every N cycles while granted, in case the "
            "output device was restarted underneath us. 0 disables.",
    )

    ProxyTimeout = device_property(
        dtype='int', default_value=800,
        doc="Milliseconds a read or command may block for. This is what sets "
            "how long a trip takes when the input device hangs rather than "
            "answering: the worst case is "
            "MaxReadFailures * (ProxyTimeout + PollPeriod), so 800 ms with the "
            "other defaults gives about 5 s. Keep that comfortably below the "
            "output device's DeadmanTimeout, or the deadman fires first and "
            "recovery needs a fresh On() instead of just the flow coming back. "
            "The old 3000 ms default gave 12 s, which lost that race.",
    )

    # ----------
    # Attributes
    # ----------

    InputValue = attribute(dtype='double', label="InputValue", format="%6.2f")
    Permit = attribute(dtype='bool', label="Permit")
    Tripped = attribute(dtype='bool', label="Tripped")
    LastTripTime = attribute(dtype='str', label="LastTripTime")
    LastTripValue = attribute(dtype='double', label="LastTripValue", format="%6.2f")
    LastTripReason = attribute(dtype='str', label="LastTripReason")
    ThresholdOnRB = attribute(dtype='double', label="ThresholdOn", format="%6.2f")
    ThresholdOffRB = attribute(dtype='double', label="ThresholdOff", format="%6.2f")

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(AnalogInterlock.init_device) ENABLED START #
        self.stop_event = threading.Event()
        self.stop_event.set()
        self.ctrlloop = None

        self.inputvalue = float('nan')
        self.permit = False
        self.tripped = False
        self.lasttriptime = "never"
        self.lasttripvalue = float('nan')
        self.lasttripreason = ""

        self.readfailures = 0
        self.beatfailures = 0
        self.stalecount = 0
        self.manuallatch = False
        self.lastheartbeat = None
        self.cyclessincereassert = 0

        self.inputproxy = None
        self.outputproxy = None

        if self.ThresholdOff >= self.ThresholdOn:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("ThresholdOff (%g) must be below ThresholdOn (%g)"
                            % (self.ThresholdOff, self.ThresholdOn))
            return

        # Deliberately no command is sent here. This server restarting must not
        # by itself disturb a running experiment: the output device keeps
        # whatever state it had, and the first cycle a fraction of a second
        # later decides on the basis of a real reading. If this server stays
        # down, the output device's deadman is what de-asserts the permissive.
        self.set_state(PyTango.DevState.INIT)
        self.set_status("Waiting for first reading")

        self.stop_event.clear()
        self.ctrlloop = ControlThread(self)
        self.ctrlloop.start()
        # PROTECTED REGION END #    //  AnalogInterlock.init_device

    # PROTECTED REGION ID(AnalogInterlock.protected_methods) ENABLED START #
    def proxy(self, which):
        """Create device proxies lazily, so a database or device that is not up
        yet delays the interlock rather than killing it at start-up."""
        if which == "input":
            if self.inputproxy is None:
                self.inputproxy = PyTango.DeviceProxy(self.InputDevice)
                self.inputproxy.set_timeout_millis(self.ProxyTimeout)
            return self.inputproxy
        if self.outputproxy is None:
            self.outputproxy = PyTango.DeviceProxy(self.OutputDevice)
            self.outputproxy.set_timeout_millis(self.ProxyTimeout)
        return self.outputproxy

    def send(self, cmd):
        try:
            self.proxy("output").command_inout(cmd)
            return True
        except Exception as exc:
            self.outputproxy = None
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Cannot command %s on %s: %s"
                            % (cmd, self.OutputDevice, exc))
            return False

    def trip(self, reason, state=PyTango.DevState.ALARM):
        """De-assert the permissive and record why. Idempotent."""
        waspermit = self.permit
        wastripped = self.tripped
        self.permit = False
        self.tripped = True
        # Record when a granted permissive is dropped, and also on the first
        # trip of a condition that was never granted in the first place -- the
        # commissioning procedure closes the valve from cold and expects
        # LastTripReason to say so. Not on every repeat, or an outage lasting
        # minutes would keep overwriting the timestamp of its own first cycle.
        if waspermit or not wastripped:
            self.lasttriptime = time.strftime("%Y-%m-%d %H:%M:%S")
            self.lasttripvalue = self.inputvalue
            self.lasttripreason = reason
        self.send(self.OffCommand)
        if self.get_state() != PyTango.DevState.FAULT or state == PyTango.DevState.FAULT:
            self.set_state(state)
            self.set_status(reason)

    def grant(self):
        if not self.send(self.OnCommand):
            return
        self.permit = True
        self.tripped = False
        self.cyclessincereassert = 0
        self.set_state(PyTango.DevState.ON)
        self.set_status("Permit granted (%s = %.2f)"
                        % (self.InputAttribute, self.inputvalue))

    def cycle(self):
        """One poll. Called only from the control thread."""
        # --- read the input -------------------------------------------------
        try:
            reading = self.proxy("input").read_attribute(self.InputAttribute)
            if reading.quality == PyTango.AttrQuality.ATTR_INVALID:
                raise ValueError("attribute quality is INVALID")
            value = float(reading.value)
        except Exception as exc:
            self.inputproxy = None
            self.readfailures += 1
            if self.readfailures >= self.MaxReadFailures:
                self.trip("Cannot read %s/%s (%d consecutive failures): %s"
                          % (self.InputDevice, self.InputAttribute,
                             self.readfailures, exc),
                          PyTango.DevState.FAULT)
            return
        self.readfailures = 0
        self.inputvalue = value

        # --- is the publisher still alive? ----------------------------------
        if self.HeartbeatAttribute:
            try:
                beat = self.proxy("input").read_attribute(
                    self.HeartbeatAttribute).value
                self.beatfailures = 0
            except Exception as exc:
                # A heartbeat that is configured but cannot be read is a
                # failure, not an absent heartbeat. Swallowing it would leave
                # this server reporting ON while silently unable to tell a live
                # publisher from a frozen one -- the single thing it exists to
                # detect. Set HeartbeatAttribute to "" to disable it on purpose.
                # Returning here also skips the keepalive below, on purpose:
                # while the state of the publisher is unknown there is no
                # reason to go on reassuring the output device's deadman.
                self.beatfailures += 1
                if self.beatfailures >= self.MaxReadFailures:
                    self.trip("Cannot read heartbeat %s/%s (%d consecutive "
                              "failures): %s. Staleness cannot be detected, so "
                              "the reading of %.2f cannot be trusted"
                              % (self.InputDevice, self.HeartbeatAttribute,
                                 self.beatfailures, exc, value),
                              PyTango.DevState.FAULT)
                return
            if beat == self.lastheartbeat:
                self.stalecount += 1
            else:
                self.stalecount = 0
                self.lastheartbeat = beat
            if self.stalecount >= self.StaleCycles:
                self.trip("%s/%s frozen for %d cycles; the reading of "
                          "%.2f cannot be trusted"
                          % (self.InputDevice, self.HeartbeatAttribute,
                             self.stalecount, value))
                return

        # --- threshold with hysteresis --------------------------------------
        latched = self.manuallatch or (self.Latching and self.tripped)
        if self.permit:
            if value < self.ThresholdOff:
                self.trip("%s = %.2f below ThresholdOff (%.2f)"
                          % (self.InputAttribute, value, self.ThresholdOff))
                return
        else:
            if value > self.ThresholdOn and not latched:
                self.grant()

        # --- maintain the permissive ----------------------------------------
        if self.permit:
            if self.KeepaliveCommand:
                self.send(self.KeepaliveCommand)
            if self.ReassertCycles > 0:
                self.cyclessincereassert += 1
                if self.cyclessincereassert >= self.ReassertCycles:
                    self.cyclessincereassert = 0
                    self.send(self.OnCommand)
            return

        # Not granted and nothing tripped this cycle: the input is readable but
        # still inside the hysteresis band. Report that explicitly, rather than
        # leaving whatever state an earlier failure set, which would otherwise
        # leave the device stuck in FAULT while reading perfectly well.
        self.set_state(PyTango.DevState.ALARM)
        if latched:
            self.set_status("No permit: latched off, Reset to clear (%s = %.2f)"
                            % (self.InputAttribute, value))
        else:
            self.set_status("No permit: %s = %.2f, must rise above %.2f"
                            % (self.InputAttribute, value, self.ThresholdOn))
    # PROTECTED REGION END #    //  AnalogInterlock.protected_methods

    def always_executed_hook(self):
        # PROTECTED REGION ID(AnalogInterlock.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  AnalogInterlock.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(AnalogInterlock.delete_device) ENABLED START #
        self.stop_event.set()
        if self.ctrlloop is not None and self.ctrlloop.is_alive():
            self.ctrlloop.join(timeout=2.0 + self.PollPeriod)
        # Stopping deliberately does NOT de-assert the permissive: an Init from
        # Jive would otherwise trip a running experiment. Keepalives stop, so
        # the output device's deadman takes over if this server does not come
        # back.
        self.permit = False
        # PROTECTED REGION END #    //  AnalogInterlock.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_InputValue(self):
        # PROTECTED REGION ID(AnalogInterlock.InputValue_read) ENABLED START #
        if self.readfailures > 0:
            return (self.inputvalue, time.time(),
                    PyTango.AttrQuality.ATTR_INVALID)
        return self.inputvalue
        # PROTECTED REGION END #    //  AnalogInterlock.InputValue_read

    def read_Permit(self):
        # PROTECTED REGION ID(AnalogInterlock.Permit_read) ENABLED START #
        return self.permit
        # PROTECTED REGION END #    //  AnalogInterlock.Permit_read

    def read_Tripped(self):
        # PROTECTED REGION ID(AnalogInterlock.Tripped_read) ENABLED START #
        return self.tripped
        # PROTECTED REGION END #    //  AnalogInterlock.Tripped_read

    def read_LastTripTime(self):
        # PROTECTED REGION ID(AnalogInterlock.LastTripTime_read) ENABLED START #
        return self.lasttriptime
        # PROTECTED REGION END #    //  AnalogInterlock.LastTripTime_read

    def read_LastTripValue(self):
        # PROTECTED REGION ID(AnalogInterlock.LastTripValue_read) ENABLED START #
        return self.lasttripvalue
        # PROTECTED REGION END #    //  AnalogInterlock.LastTripValue_read

    def read_LastTripReason(self):
        # PROTECTED REGION ID(AnalogInterlock.LastTripReason_read) ENABLED START #
        return self.lasttripreason
        # PROTECTED REGION END #    //  AnalogInterlock.LastTripReason_read

    def read_ThresholdOnRB(self):
        # PROTECTED REGION ID(AnalogInterlock.ThresholdOnRB_read) ENABLED START #
        return self.ThresholdOn
        # PROTECTED REGION END #    //  AnalogInterlock.ThresholdOnRB_read

    def read_ThresholdOffRB(self):
        # PROTECTED REGION ID(AnalogInterlock.ThresholdOffRB_read) ENABLED START #
        return self.ThresholdOff
        # PROTECTED REGION END #    //  AnalogInterlock.ThresholdOffRB_read

    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def Reset(self):
        # PROTECTED REGION ID(AnalogInterlock.Reset) ENABLED START #
        # Only meaningful with Latching = True. Clears the software latch; it
        # has no effect on any hardware latch, which still needs its button.
        self.tripped = False
        self.manuallatch = False
        self.readfailures = 0
        self.beatfailures = 0
        self.stalecount = 0
        self.lastheartbeat = None
        self.set_state(PyTango.DevState.INIT)
        self.set_status("Latch cleared, waiting for next reading")
        # PROTECTED REGION END #    //  AnalogInterlock.Reset

    @command(
    )
    @DebugIt()
    def Trip(self):
        # PROTECTED REGION ID(AnalogInterlock.Trip) ENABLED START #
        # Manual de-assert, e.g. to test the chain without touching the water.
        # This latches whatever the Latching property says: a person asked for
        # the permissive to drop, so it stays down until a person clears it with
        # Reset. Without this the next cycle would re-grant it a second later
        # and the test would look like it had not worked.
        self.manuallatch = True
        self.trip("Tripped manually; Reset to clear")
        # PROTECTED REGION END #    //  AnalogInterlock.Trip

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(AnalogInterlock.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((AnalogInterlock,), args=args, **kwargs)
    # PROTECTED REGION END #    //  AnalogInterlock.main


if __name__ == '__main__':
    main()
