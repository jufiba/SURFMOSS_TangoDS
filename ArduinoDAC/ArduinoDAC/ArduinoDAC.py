# -*- coding: utf-8 -*-
#
# This file is part of the ArduinoDAC project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" ArduinoDAC

Server for a simple interface of an Arduino connected to a DAC
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
# PROTECTED REGION ID(ArduinoDAC.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  ArduinoDAC.additionnal_import

__all__ = ["ArduinoDAC", "main"]


class ArduinoDAC(Device):
    """
    Server for a simple interface of an Arduino connected to a DAC
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(ArduinoDAC.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  ArduinoDAC.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str',
    )

    ScaleFactorMin = device_property(
        dtype='float', default_value=32815
    )

    ScaleFactorMax = device_property(
        dtype='float', default_value=50350
    )

    Range = device_property(
        dtype='float', default_value=30.0
    )

    # ----------
    # Attributes
    # ----------

    Output = attribute(
        dtype='double',
        access=AttrWriteType.WRITE,
        label="Current",
        unit="A",
        display_unit="%4.2e",
        max_value=30.00,
        min_value=0.00,
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(ArduinoDAC.init_device) ENABLED START #
        try:
            self.ser=serial.Serial(self.SerialPort,baudrate=9600,bytesize=8,parity="N",stopbits=1,timeout=1)
        except:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Can't connect to ArduinoDAC")
            self.debug_stream("Can't connect to ArduinoDAC")
            return
        self.set_status("Connected to ArduinoDAC")
        self.debug_stream("Connected to ArduinoDAC")
        
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  ArduinoDAC.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(ArduinoDAC.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  ArduinoDAC.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(ArduinoDAC.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  ArduinoDAC.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def write_Output(self, value):
        # PROTECTED REGION ID(ArduinoDAC.Output_write) ENABLED START #
        output=int(value*(self.ScaleFactorMax-self.ScaleFactorMin)/self.Range+self.ScaleFactorMin)
        self.ser.write(bytes("*DAC %d\n"%output,encoding="ascii"))
        
        # PROTECTED REGION END #    //  ArduinoDAC.Output_write


    # --------
    # Commands
    # --------

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(ArduinoDAC.main) ENABLED START #
    return run((ArduinoDAC,), args=args, **kwargs)
    # PROTECTED REGION END #    //  ArduinoDAC.main

if __name__ == '__main__':
    main()
