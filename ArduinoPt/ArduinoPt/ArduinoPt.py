# -*- coding: utf-8 -*-
#
# This file is part of the ArduinoPt project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" ArduinoPt

An Arduino connected to a Pt module.
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
# PROTECTED REGION ID(ArduinoPt.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  ArduinoPt.additionnal_import

__all__ = ["ArduinoPt", "main"]


class ArduinoPt(Device):
    """
    An Arduino connected to a Pt module.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(ArduinoPt.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  ArduinoPt.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str', default_value="/dev/ttyS0"
    )

    # ----------
    # Attributes
    # ----------

    Temperature = attribute(
        dtype='double',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(ArduinoPt.init_device) ENABLED START #
        self.ser=serial.Serial(self.SerialPort,9600,bytesize=8,parity="N",stopbits=1,timeout=5)
        try:
            self.ser.write("*PT\n")
            pt=self.ser.readline();
            if (pt=="Fault"):
                self.set_state(PyTango.DevState.FAULT)
                self.set_status("No Pt resistor connected")
                self.debug_stream("No Pt resistor connected to Arduino")
            else:
                self.set_state(PyTango.DevState.ON)
                self.set_status("Pt resistor connected")
                self.debug_stream("Pt resistor connected to Arduino")
        except:
            self.set_state(PyTango.DevState.OFF)
            self.set_status("No response from Arduino")
            self.debug_stream("No response from Arduino")
        # PROTECTED REGION END #    //  ArduinoPt.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(ArduinoPt.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  ArduinoPt.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(ArduinoPt.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  ArduinoPt.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Temperature(self):
        # PROTECTED REGION ID(ArduinoPt.Temperature_read) ENABLED START #
        try:
            self.ser.write("*PT\n")
            pt=self.ser.readline();
            if (pt=="Fault"):
                self.set_state(PyTango.DevState.FAULT)
                self.set_status("No Pt1000 resistor connected")
                self.debug_stream("No Pt1000 resistor connected to Arduino")
                return(0.0)
            else:
                return(float(pt))
        except:
            self.set_state(PyTango.DevState.OFF)
            self.set_status("No response from Arduino")
            self.debug_stream("No response from Arduino")
            return(0.0)
        # PROTECTED REGION END #    //  ArduinoPt.Temperature_read


    # --------
    # Commands
    # --------

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(ArduinoPt.main) ENABLED START #
    return run((ArduinoPt,), args=args, **kwargs)
    # PROTECTED REGION END #    //  ArduinoPt.main

if __name__ == '__main__':
    main()
