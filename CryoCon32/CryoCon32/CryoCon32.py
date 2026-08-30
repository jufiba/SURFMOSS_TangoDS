# -*- coding: utf-8 -*-
#
# This file is part of the CryoCon32 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" CryoCon 32 device server

Minimalistic driver for the Cryocon32 controller used in our Mossbauer
transmission setup.

It reads and it reports. The one thing it writes at start-up is the display
units, so that the K the attributes declare is the K the controller answers
with. It used to send `LOOP 1:TYPE PID` as well, which meant every restart of
the server -- an Init from Jive included -- silently put the control loop back
into PID. How the cryostat is controlled is the operator's decision, not a
side effect of a server starting.

A channel the controller cannot measure is answered with a row of dashes,
"-------": an open sensor, one out of range, or nothing wired to it. That is
an honest "no reading" and it reads INVALID here. It used to reach the client
as `ValueError: could not convert string to float: b'-------\n'`, which made
an unplugged sensor look like a broken server.
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
# PROTECTED REGION ID(CryoCon32.additionnal_import) ENABLED START #
import os
import sys
import time
import serial

# Seconds between attempts to reopen the port while the server is in FAULT.
RETRY_PERIOD = 10
# PROTECTED REGION END #    //  CryoCon32.additionnal_import

__all__ = ["CryoCon32", "main"]


class CryoCon32(Device):
    """
    Minimalistic driver for the Cryocon32 controller used in our Mossbauer transmission setup.
    """
    # PROTECTED REGION ID(CryoCon32.class_variable) ENABLED START #
    # class_variable is the only region inside the class body that POGO
    # preserves, so the helpers live here.

    # How often the control loop's on/off state is re-read. The state of this
    # device is the state of that loop, and it was only ever read at start-up:
    # switching the controller off left the server saying ON until somebody
    # ran an Init.
    CONTROL_SECONDS = 1.0

    def _fail(self, reason):
        self.set_state(tango.DevState.FAULT)
        self.set_status(reason)
        self.error_stream(reason)
        return False

    def _connect(self):
        """Open the port and identify the controller. True if it worked.

        Kept out of init_device so that a controller which is switched off or
        unplugged at start-up is picked up later without an operator Init.
        """
        self.lastconnect = time.time()
        self.lastcontrol = 0.0
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        try:
            self.ser = serial.Serial(self.SerialPort, self.SerialSpeed,
                                     bytesize=8, parity="N", stopbits=1,
                                     timeout=0.5)
            idn = self._query(b"*IDN?\n")
            if not idn.startswith("Cryocon Model 32"):
                return self._fail("Not a CryoCon32 on %s: it answered %r"
                                  % (self.SerialPort, idn))
            # The only writes at start-up, and both are presentation: the
            # attributes declare K, so the controller is asked to report K.
            # Channel B was left out before, so its declared unit was never
            # actually enforced.
            self.ser.write(b"INPUT A:UNITS K\n")
            self.ser.write(b"INPUT B:UNITS K\n")
        except serial.SerialException as exc:
            return self._fail("Can't open %s: %s" % (self.SerialPort, exc))
        except Exception as exc:
            return self._fail("Can't talk to the CryoCon32 on %s: %s"
                              % (self.SerialPort, exc))
        self.problems = {}
        self._refresh_control(force=True)
        self._describe()
        self.debug_stream("Connected to CryoCon32 on %s" % self.SerialPort)
        return True

    def _require_port(self):
        if self.ser is None:
            tango.Except.throw_exception(
                "CryoCon32_NotConnected",
                "No connection to the CryoCon32 on %s" % self.SerialPort,
                "CryoCon32")

    def _query(self, command):
        """Send a query and return its one-line answer, stripped.

        The input buffer is cleared first: a reply that arrived late, or one
        nobody read, would otherwise be handed to the next query and every
        reading after it would be one place out.
        """
        self._require_port()
        self.ser.reset_input_buffer()
        self.ser.write(command)
        return self.ser.readline().decode("ascii", "replace").strip()

    def _number(self, command):
        """The reply as a float, or None if the controller did not give one.

        Values come back with the unit stuck on the end -- "20.000000K" -- so
        trailing letters are dropped rather than a fixed two characters, which
        would quietly mangle the number if the controller were ever in C.
        """
        reply = self._query(command)
        self.lastreply = reply
        while reply and reply[-1].isalpha():
            reply = reply[:-1]
        try:
            return float(reply)
        except ValueError:
            return None

    def _describe(self):
        """Status from what is wrong right now, so two channels do not fight.

        Writing the status straight from each read made A and B overwrite each
        other every sweep, and whichever ran last decided what the device
        appeared to be doing.
        """
        if self.problems:
            self.set_status("; ".join(self.problems[k]
                                      for k in sorted(self.problems)))
        else:
            self.set_status("Connected to CryoCon32 on %s" % self.SerialPort)

    def _note(self, key, problem):
        if problem is None:
            self.problems.pop(key, None)
        else:
            self.problems[key] = problem
        self._describe()

    def _refresh_control(self, force=False):
        """State follows the control loop, re-read at most once a second."""
        now = time.time()
        if not force and now - self.lastcontrol < self.CONTROL_SECONDS:
            return
        self.lastcontrol = now
        mode = self._query(b"CONTROL?\n")
        self.set_state(tango.DevState.OFF if mode.upper().startswith("OFF")
                       else tango.DevState.ON)

    def _read(self, command, key, what):
        """One numeric reading, or INVALID with the reason in the status."""
        try:
            value = self._number(command)
        except Exception as exc:
            self._fail("Lost the CryoCon32 on %s: %s" % (self.SerialPort, exc))
            return (0.0, time.time(), tango.AttrQuality.ATTR_INVALID)
        if value is None:
            self._note(key, "%s is not reading: the controller answers %r"
                       % (what, self.lastreply))
            return (0.0, time.time(), tango.AttrQuality.ATTR_INVALID)
        self._note(key, None)
        return value
    # PROTECTED REGION END #    //  CryoCon32.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str', default_value="/dev/ttyS0"
    )

    SerialSpeed = device_property(
        dtype='uint16', default_value=9600
    )

    # ----------
    # Attributes
    # ----------

    TemperatureA = attribute(
        dtype='double',
        unit="K",
        standard_unit="K",
        display_unit="K",
        format="%4.1f",
        max_value=1000.0,
        min_value=0.0,
    )

    SetPoint = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        label="SetPoint",
        unit="K",
        standard_unit="K",
        display_unit="K",
        format="%4.1f",
        max_value=1000.0,
        min_value=0.0,
    )

    TemperatureB = attribute(
        dtype='double',
        unit="K",
    )

    HeaterLevel = attribute(
        dtype='DevEnum',
        access=AttrWriteType.READ_WRITE,
        enum_labels=["LOW", "MID", "HIGH", ],
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(CryoCon32.init_device) ENABLED START #
        self.ser = None
        self.problems = {}
        self.lastreply = ""
        self.lastconnect = 0.0
        self.lastcontrol = 0.0
        self._connect()
        # PROTECTED REGION END #    //  CryoCon32.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(CryoCon32.always_executed_hook) ENABLED START #
        # Where a controller that was off or unplugged at start-up is picked
        # up without an operator Init, and where the state catches up with the
        # control loop being switched on or off at the front panel.
        if self.get_state() == tango.DevState.FAULT:
            if time.time() - self.lastconnect > RETRY_PERIOD:
                self._connect()
            return
        try:
            self._refresh_control()
        except Exception as exc:
            self._fail("Lost the CryoCon32 on %s: %s" % (self.SerialPort, exc))
        # PROTECTED REGION END #    //  CryoCon32.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(CryoCon32.delete_device) ENABLED START #
        # Guarded: if the port never opened there is nothing to close, and an
        # AttributeError here would come out of an Init as a puzzling error
        # about the wrong thing.
        try:
            if self.ser is not None:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        # PROTECTED REGION END #    //  CryoCon32.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_TemperatureA(self):
        # PROTECTED REGION ID(CryoCon32.TemperatureA_read) ENABLED START #
        return self._read(b"INPUT? A\n", "A", "Channel A")
        # PROTECTED REGION END #    //  CryoCon32.TemperatureA_read

    def read_SetPoint(self):
        # PROTECTED REGION ID(CryoCon32.SetPoint_read) ENABLED START #
        return self._read(b"LOOP 1:SETPT?\n", "setpoint", "The setpoint")
        # PROTECTED REGION END #    //  CryoCon32.SetPoint_read

    def write_SetPoint(self, value):
        # PROTECTED REGION ID(CryoCon32.SetPoint_write) ENABLED START #
        self._require_port()
        self.ser.write(("LOOP 1:SETPT %f \n" % (value)).encode("ascii"))
        # PROTECTED REGION END #    //  CryoCon32.SetPoint_write

    def read_TemperatureB(self):
        # PROTECTED REGION ID(CryoCon32.TemperatureB_read) ENABLED START #
        return self._read(b"INPUT? B\n", "B", "Channel B")
        # PROTECTED REGION END #    //  CryoCon32.TemperatureB_read

    def read_HeaterLevel(self):
        # PROTECTED REGION ID(CryoCon32.HeaterLevel_read) ENABLED START #
        # The old code ended in a bare `else: return 2`, so any answer it did
        # not recognise -- including an empty one from a controller that had
        # stopped talking -- was reported as HIGH.
        try:
            res = self._query(b"LOOP 1:RANGE?\n").upper()
        except Exception as exc:
            self._fail("Lost the CryoCon32 on %s: %s" % (self.SerialPort, exc))
            return (0, time.time(), tango.AttrQuality.ATTR_INVALID)
        levels = {"LOW": 0, "MID": 1, "HI": 2, "HIGH": 2}
        if res not in levels:
            self._note("range", "the heater range is unreadable: the "
                                "controller answers %r" % res)
            return (0, time.time(), tango.AttrQuality.ATTR_INVALID)
        self._note("range", None)
        return levels[res]
        # PROTECTED REGION END #    //  CryoCon32.HeaterLevel_read

    def write_HeaterLevel(self, value):
        # PROTECTED REGION ID(CryoCon32.HeaterLevel_write) ENABLED START #
        self._require_port()
        if (value==0):
            self.ser.write(b"LOOP 1:RANGE LOW\n")
        elif (value==1):
            self.ser.write(b"LOOP 1:RANGE MID\n")
        elif (value==2):
            self.ser.write(b"LOOP 1:RANGE HI\n")
        return
        # PROTECTED REGION END #    //  CryoCon32.HeaterLevel_write


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def On(self):
        # PROTECTED REGION ID(CryoCon32.On) ENABLED START #
        self._require_port()
        self.ser.write(b"CONTROL ON\n")
        self.set_state(tango.DevState.ON)
        pass
        # PROTECTED REGION END #    //  CryoCon32.On

    @command(
    )
    @DebugIt()
    def Off(self):
        # PROTECTED REGION ID(CryoCon32.Off) ENABLED START #
        self._require_port()
        self.ser.write(b"STOP\n")
        self.set_state(tango.DevState.OFF)
        pass
        # PROTECTED REGION END #    //  CryoCon32.Off

    @command(
    dtype_in='str', 
    )
    @DebugIt()
    def SendCmd(self, argin):
        # PROTECTED REGION ID(CryoCon32.SendCmd) ENABLED START #
        self._require_port()
        self.ser.write((argin + "\n").encode("ascii"))
        return ""
        # PROTECTED REGION END #    //  CryoCon32.SendCmd

    @command(
    dtype_in='str', 
    dtype_out='str', 
    )
    @DebugIt()
    def SendQuery(self, argin):
        # PROTECTED REGION ID(CryoCon32.SendQuery) ENABLED START #
        return self._query((argin + "\n").encode("ascii"))
        # PROTECTED REGION END #    //  CryoCon32.SendQuery

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(CryoCon32.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((CryoCon32,), args=args, **kwargs)
    # PROTECTED REGION END #    //  CryoCon32.main

if __name__ == '__main__':
    main()
