# -*- coding: utf-8 -*-
#
# This file is part of the CenterOneGauge project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" VacuumGauge

Single-Channel Vacuum Gauge
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
# PROTECTED REGION ID(CenterOneGauge.additionnal_import) ENABLED START #
import os
import sys
import time
import serial
# PROTECTED REGION END #    //  CenterOneGauge.additionnal_import

__all__ = ["CenterOneGauge", "main"]


class CenterOneGauge(Device):
    """
    Single-Channel Vacuum Gauge
    """
    # PROTECTED REGION ID(CenterOneGauge.class_variable) ENABLED START #

    def formatdata(self,str_data):
        status = str_data[0]
        data = str_data[2:]
        return status , float(data)

    def sendcommand(self, str_command):
        self.ser.write(str_command.encode("ascii"))
        resp=self.ser.read_until(b"\r\n")
        return resp.decode("ascii")


    # PROTECTED REGION END #    //  CenterOneGauge.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str',
    )

    # ----------
    # Attributes
    # ----------

    Pressure = attribute(
        dtype='double',
        label="Pressure",
        unit="mbar",
        standard_unit="mbar",
        display_unit="mbar",
        format="%4.2e",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(CenterOneGauge.init_device) ENABLED START #
        # An exception escaping init_device makes PyTango exit the whole
        # server, and the Starter then leaves it for dead. FAULT with the
        # reason instead, so an unplugged gauge leaves a device that says so.
        self.ser=None
        try:
            self.ser=serial.Serial(self.SerialPort,9600,bytesize=8,parity="N",stopbits=1,timeout=1)
        except (serial.SerialException,ValueError) as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't open %s: %s"%(self.SerialPort,e))
            self.error_stream("Can't open %s: %s"%(self.SerialPort,e))
            return
        self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  CenterOneGauge.init_device
    def always_executed_hook(self):
        # PROTECTED REGION ID(CenterOneGauge.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  CenterOneGauge.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(CenterOneGauge.delete_device) ENABLED START #
        if (self.ser is not None):
            self.ser.close()
        # PROTECTED REGION END #    //  CenterOneGauge.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Pressure(self):
        # PROTECTED REGION ID(CenterOneGauge.Pressure_read) ENABLED START #
        """Read the pressure, and make the state say what this read found.

        The state used to be set ON once in init_device and moved to OFF by a
        failed read, with nothing that could ever move it back. One transient
        exchange therefore left the device reading pressure correctly and
        reporting OFF for ever: leem/vacuum/gaugeEvap was found at 3.6 mbar,
        ATTR_VALID, state OFF, and came back ON the moment it was restarted.
        Every path here sets the state, in both directions.

        0.0 on a pressure gauge reads as perfect vacuum, which is the most
        dangerous value this attribute can hand to an interlock or an alarm:
        it says the chamber is fine at exactly the moment nothing is known.
        Every path with no reading returns INVALID instead. Same reasoning as
        LeyboldIG3, SEAWaterflowmeter and TempSensorDS18B20.
        """
        rcontrol = self.sendcommand("PR1 \r")
        if (not rcontrol.startswith("\x06")):
            # rcontrol[0] on an empty string was an IndexError, which is what a
            # read that times out now produces.
            self.set_state(tango.DevState.FAULT)
            self.set_status("The gauge did not acknowledge PR1: %r"%rcontrol)
            self.error_stream("The gauge did not acknowledge PR1: %r"%rcontrol)
            return (0.0,time.time(),tango.AttrQuality.ATTR_INVALID)
        rdata = self.sendcommand("\x05")
        try:
            (status,data)=self.formatdata(rdata)
        except (IndexError,ValueError) as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Unreadable answer to PR1: %r (%s)"%(rdata,e))
            self.error_stream("Unreadable answer to PR1: %r"%rdata)
            return (0.0,time.time(),tango.AttrQuality.ATTR_INVALID)
        # The first field is the measurement status, and 0 is the only value
        # that means the number after it is a reading. Confirmed against the
        # gauge: PR1 answers \x06, ENQ answers "0, 3.6000E+00". The non-zero
        # codes are not told apart here because no manual for this gauge is in
        # the repository; the code is reported verbatim so it can be looked up.
        if (status!="0"):
            self.set_state(tango.DevState.FAULT)
            self.set_status("The gauge reports measurement status %s, not 0, "
                            "so there is no reading"%status)
            self.debug_stream("The gauge reports measurement status %s"%status)
            return (0.0,time.time(),tango.AttrQuality.ATTR_INVALID)
        self.set_state(tango.DevState.ON)
        return data
        # PROTECTED REGION END #    //  CenterOneGauge.Pressure_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def Reset(self):
        # PROTECTED REGION ID(CenterOneGauge.Reset) ENABLED START #
        self.set_state(tango.DevState.OFF)

        rcontrol = self.sendcommand("RES [,1] \r")
        if rcontrol[0] == "\x06":
            rdata = self.sendcommand("\x05")
            if rdata[0] == "0":
                self.set_state(tango.DevState.ON)
            else:
                return rdata

        # PROTECTED REGION END #    //  CenterOneGauge.Reset

    @command(
    dtype_in='str', 
    dtype_out='str', 
    )
    @DebugIt()
    def sendCommand(self, argin):
        # PROTECTED REGION ID(CenterOneGauge.sendCommand) ENABLED START #
        rdata = self.sendcommand(argin)			
        return rdata
        # PROTECTED REGION END #    //  CenterOneGauge.sendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(CenterOneGauge.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((CenterOneGauge,), args=args, **kwargs)
    # PROTECTED REGION END #    //  CenterOneGauge.main

if __name__ == '__main__':
    main()
