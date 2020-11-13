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
import PyTango
from PyTango import DebugIt
from PyTango.server import run
from PyTango.server import Device, DeviceMeta
from PyTango.server import attribute, command
from PyTango.server import device_property
from PyTango import AttrQuality, DispLevel, DevState
from PyTango import AttrWriteType, PipeWriteType
# Additional import
# PROTECTED REGION ID(AGPolaritySwitch.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  AGPolaritySwitch.additionnal_import

__all__ = ["AGPolaritySwitch", "main"]


class AGPolaritySwitch(Device):
    """
    A devicer server for changing the polarity of the high current (up to 30A) power supply. It is a relay box with an Arduino.
    """
    __metaclass__ = DeviceMeta
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
            resp=self.ser.readline()
            dummy=self.ser.readline()
        except:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Can't connect to AGPolaritySwitch")
            self.debug_stream("Can't connect to AGPolaritySwitch")
            return
        self.set_status("Connected to AGPolaritySwitch")
        self.debug_stream("Connected to AGPolaritySwitch")
        
        if (resp=="positive"): # Only check first gauge to set device status
            self.set_state(PyTango.DevState.ON)
        else:
            self.set_state(PyTango.DevState.OFF)
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
        resp=self.ser.readline()
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
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  AGPolaritySwitch.setPositive

    @command(
    )
    @DebugIt()
    def SetNegative(self):
        # PROTECTED REGION ID(AGPolaritySwitch.SetNegative) ENABLED START #
        self.ser.write(bytearray("*NEG\n","ascii"))
        self.set_state(PyTango.DevState.OFF)
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
        resp=self.ser.readline()
        return(resp) 
        # PROTECTED REGION END #    //  AGPolaritySwitch.sendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(AGPolaritySwitch.main) ENABLED START #
    return run((AGPolaritySwitch,), args=args, **kwargs)
    # PROTECTED REGION END #    //  AGPolaritySwitch.main

if __name__ == '__main__':
    main()
