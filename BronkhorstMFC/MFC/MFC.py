# -*- coding: utf-8 -*-
#
# This file is part of the MFC project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" KISS Mass Flow Controller Driver

Simple driver for the Bronkhorst Mass Flow Controllers.
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
# PROTECTED REGION ID(MFC.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  MFC.additionnal_import

__all__ = ["MFC", "main"]


class MFC(Device):
    """
    Simple driver for the Bronkhorst Mass Flow Controllers.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(MFC.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  MFC.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str',
        mandatory=True
    )

    # ----------
    # Attributes
    # ----------

    SetPoint = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        label="setPoint",
        unit="%",
        standard_unit="%",
        display_unit="%",
        format="%4.1f",
        max_value=100.0,
        min_value=0.0,
    )

    Measure = attribute(
        dtype='double',
        label="Measured",
        unit="%",
        standard_unit="%",
        display_unit="%",
        format="%4.1f",
        max_value=100.0,
        min_value=0.0,
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(MFC.init_device) ENABLED START #
	self.ser=serial.Serial(self.SerialPort,baudrate=38400,bytesize=8,parity="N",stopbits=1)
	self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  MFC.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(MFC.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  MFC.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(MFC.delete_device) ENABLED START #
 	self.ser.close()
        pass
        # PROTECTED REGION END #    //  MFC.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_SetPoint(self):
        # PROTECTED REGION ID(MFC.SetPoint_read) ENABLED START #
	message=":06800401210121\r\n"
        self.ser.write(message)
        response=self.ser.readline()
        value=int(response[11:15],16)
        return(value/320.0)
        # PROTECTED REGION END #    //  MFC.SetPoint_read

    def write_SetPoint(self, value):
        # PROTECTED REGION ID(MFC.SetPoint_write) ENABLED START #
	value=int(320.0*value)
        hx='{:04x}'.format(value)
        message=":0680010121"+hx+"\r\n"
        self.ser.write(message)
        response=self.ser.readline()
        print response
        # PROTECTED REGION END #    //  MFC.SetPoint_write

    def read_Measure(self):
        # PROTECTED REGION ID(MFC.Measure_read) ENABLED START #
	message=":06800401210120\r\n"
        self.ser.write(message)
        response=self.ser.readline()
        value=int(response[11:15],16)
        return(value/320.0)
        # PROTECTED REGION END #    //  MFC.Measure_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def Blink(self):
        # PROTECTED REGION ID(MFC.Blink) ENABLED START #
        message=":06800100600139\r\n"
        self.ser.write(message)
        response=self.ser.readline()
        print response
        # PROTECTED REGION END #    //  MFC.Blink

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(MFC.main) ENABLED START #
    return run((MFC,), args=args, **kwargs)
    # PROTECTED REGION END #    //  MFC.main

if __name__ == '__main__':
    main()
