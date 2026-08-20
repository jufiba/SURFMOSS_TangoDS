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
        resp=self.ser.read_until(terminator=b"\r\n")
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
        self.ser=serial.Serial(self.SerialPort,9600,bytesize=8,parity="N",stopbits=1)
        self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  CenterOneGauge.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(CenterOneGauge.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  CenterOneGauge.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(CenterOneGauge.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  CenterOneGauge.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Pressure(self):
        # PROTECTED REGION ID(CenterOneGauge.Pressure_read) ENABLED START #
        rcontrol = self.sendcommand("PR1 \r")

        if rcontrol[0] == "\x06":
            rdata = self.sendcommand("\x05")
            status, data = self.formatdata(rdata)
        else:
            self.set_state(tango.DevState.OFF)
            data = 0.0

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
