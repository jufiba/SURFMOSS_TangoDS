# -*- coding: utf-8 -*-
#
# This file is part of the AGPolaritySwitch project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" AGPolaritySwitch

A devicer server for changing the polarity of the high current (up to 30A) power supply. It is a relay box with an Arduino.
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
# PROTECTED REGION ID(AGPolaritySwitch.additionnal_import) ENABLED START #
import os
import sys
import serial
# PROTECTED REGION END #    //  AGPolaritySwitch.additionnal_import

__all__ = ["AGPolaritySwitch", "main"]


class AGPolaritySwitch(Device):
    """
    A devicer server for changing the polarity of the high current (up to 30A) power supply. It is a relay box with an Arduino.
    """
    # PROTECTED REGION ID(AGPolaritySwitch.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  AGPolaritySwitch.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str',
    )

    Speed = device_property(
        dtype='uint16',
    )

    # ----------
    # Attributes
    # ----------

    Polarity = attribute(
        dtype='str',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(AGPolaritySwitch.init_device) ENABLED START #
        try:
            self.ser=serial.Serial(self.SerialPort,baudrate=self.Speed,bytesize=8,parity="N",stopbits=1,timeout=1)
            self.ser.write(bytearray("*STAT?\n","ascii"))
            resp=self.ser.readline().decode("ascii").strip()
            dummy=self.ser.readline()
        except:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't connect to AGPolaritySwitch")
            self.debug_stream("Can't connect to AGPolaritySwitch")
            return
        self.set_status("Connected to AGPolaritySwitch")
        self.debug_stream("Connected to AGPolaritySwitch")
        
        if (resp=="positive"): # Only check first gauge to set device status
            self.set_state(tango.DevState.ON)
        else:
            self.set_state(tango.DevState.OFF)
        # PROTECTED REGION END #    //  AGPolaritySwitch.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(AGPolaritySwitch.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  AGPolaritySwitch.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(AGPolaritySwitch.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  AGPolaritySwitch.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Polarity(self):
        # PROTECTED REGION ID(AGPolaritySwitch.Polarity_read) ENABLED START #
        self.ser.write(bytearray("*STAT?\n","ascii"))
        resp=self.ser.readline().decode("ascii").strip()
        dummy=self.ser.readline()
        return resp
        # PROTECTED REGION END #    //  AGPolaritySwitch.Polarity_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def setPositive(self):
        # PROTECTED REGION ID(AGPolaritySwitch.setPositive) ENABLED START #
        self.ser.write(bytearray("*POS\n","ascii"))
        self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  AGPolaritySwitch.setPositive

    @command(
    )
    @DebugIt()
    def SetNegative(self):
        # PROTECTED REGION ID(AGPolaritySwitch.SetNegative) ENABLED START #
        self.ser.write(bytearray("*NEG\n","ascii"))
        self.set_state(tango.DevState.OFF)
        # PROTECTED REGION END #    //  AGPolaritySwitch.SetNegative

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def sendCommand(self, argin):
        # PROTECTED REGION ID(AGPolaritySwitch.sendCommand) ENABLED START #
        self.ser.write(bytearray(argin+"\n","ascii"))
        resp=self.ser.readline().decode("ascii").strip()
        return(resp)
        # PROTECTED REGION END #    //  AGPolaritySwitch.sendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(AGPolaritySwitch.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((AGPolaritySwitch,), args=args, **kwargs)
    # PROTECTED REGION END #    //  AGPolaritySwitch.main

if __name__ == '__main__':
    main()
