# -*- coding: utf-8 -*-
#
# This file is part of the GammaIonPump project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" GammaIonPump

Simple controller for running the Gamma Vacuum Ion Pump Controllers.
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
# PROTECTED REGION ID(GammaIonPump.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  GammaIonPump.additionnal_import

__all__ = ["GammaIonPump", "main"]


class GammaIonPump(Device):
    """
    Simple controller for running the Gamma Vacuum Ion Pump Controllers.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(GammaIonPump.class_variable) ENABLED START #

    def sendcommand(self,cmd):
        # Asume command is an string in hexadecimal, say C4.
        # data is a string with an ASCII number, for example. 
        cmd_string="~"+cmd+self.crc_code(cmd)+"\r"
        self.ser.write(cmd_string)
        resp=self.ser.read_until(terminator="\r")
        return(resp)

    def crc_code(self,a):
        result=0
        for i in range(0,len(a)):
            result = result + ord(a[i])
            result%=256
        return("%02x"%result)


    # PROTECTED REGION END #    //  GammaIonPump.class_variable

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
        unit="mbar",
        standard_unit="mbar",
        display_unit="mbar",
        format="%4.2e",
    )

    Current = attribute(
        dtype='double',
        standard_unit="A",
        format="%4.2e",
    )

    Voltage = attribute(
        dtype='double',
        unit="V",
    )

    SupplyStatus = attribute(
        dtype='str',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(GammaIonPump.init_device) ENABLED START #
        self.ser=serial.Serial(self.SerialPort,baudrate=9600,bytesize=8,parity="N",stopbits=1)
        if (self.sendcommand(" 05 61 1 ")[9:-4])=="YES":
            self.set_state(PyTango.DevState.ON)
        else:
            self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  GammaIonPump.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(GammaIonPump.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  GammaIonPump.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(GammaIonPump.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  GammaIonPump.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Pressure(self):
        # PROTECTED REGION ID(GammaIonPump.Pressure_read) ENABLED START #
        result=self.sendcommand(" 05 0B 1 ")
        return float(result.split()[3])
        # PROTECTED REGION END #    //  GammaIonPump.Pressure_read

    def read_Current(self):
        # PROTECTED REGION ID(GammaIonPump.Current_read) ENABLED START #
        result=self.sendcommand(" 05 0A 1 ")
        return float(result.split()[3])
        # PROTECTED REGION END #    //  GammaIonPump.Current_read

    def read_Voltage(self):
        # PROTECTED REGION ID(GammaIonPump.Voltage_read) ENABLED START #
        result=self.sendcommand(" 05 0C 1 ")
        return float(result.split()[3])
        # PROTECTED REGION END #    //  GammaIonPump.Voltage_read

    def read_SupplyStatus(self):
        # PROTECTED REGION ID(GammaIonPump.SupplyStatus_read) ENABLED START #
        result=self.sendcommand(" 05 0D 1 ")
        return result[9:-4]
        # PROTECTED REGION END #    //  GammaIonPump.SupplyStatus_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def On(self):
        # PROTECTED REGION ID(GammaIonPump.On) ENABLED START #
        self.sendcommand(" 05 37 1 ")
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  GammaIonPump.On

    @command(
    )
    @DebugIt()
    def Off(self):
        # PROTECTED REGION ID(GammaIonPump.Off) ENABLED START #
        self.sendcommand(" 05 38 1 ")
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  GammaIonPump.Off

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def send_command(self, argin):
        # PROTECTED REGION ID(GammaIonPump.send_command) ENABLED START #
        res=self.sendcommand(argin)
        return res
        # PROTECTED REGION END #    //  GammaIonPump.send_command

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(GammaIonPump.main) ENABLED START #
    return run((GammaIonPump,), args=args, **kwargs)
    # PROTECTED REGION END #    //  GammaIonPump.main

if __name__ == '__main__':
    main()
