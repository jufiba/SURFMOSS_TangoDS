# -*- coding: utf-8 -*-
#
# This file is part of the CryoCon32 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" CryoCon 32 device server

Minimalistic driver for the Cryocon32 controller used in our Mossbauer transmission setup.
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
# PROTECTED REGION ID(CryoCon32.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  CryoCon32.additionnal_import

__all__ = ["CryoCon32", "main"]


class CryoCon32(Device):
    """
    Minimalistic driver for the Cryocon32 controller used in our Mossbauer transmission setup.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(CryoCon32.class_variable) ENABLED START #      
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
        try:
            self.ser=serial.Serial(self.SerialPort,self.SerialSpeed,bytesize=8,parity="N",stopbits=1,timeout=0.5)
            self.ser.write("*IDN?\n")
            idn=self.ser.readline()
            if (idn[0:16]!="Cryocon Model 32"):
                self.set_status("Not a CryoCon32 on serial port")
                self.debug_stream("Not a CryoCon32 on serial port")
                return
            self.ser.write("INPUT A:UNITS K\n")
            self.ser.write("LOOP 1:TYPE PID\n")
            self.ser.write("CONTROL?\n")
            mode=self.ser.readline()
            if mode[0:3]=="OFF":
                self.set_state(PyTango.DevState.OFF)
            else:
                self.set_state(PyTango.DevState.ON)
        except:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Can't connect to CryoCon32")
            self.debug_stream("Can't connect to CryoCon32")
            return
        self.set_status("Connected to CryoCon32")
        self.debug_stream("Connected to CryoCon32")
        # PROTECTED REGION END #    //  CryoCon32.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(CryoCon32.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  CryoCon32.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(CryoCon32.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  CryoCon32.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_TemperatureA(self):
        # PROTECTED REGION ID(CryoCon32.TemperatureA_read) ENABLED START #
        self.ser.write("INPUT? A\n")
        temperature=float(self.ser.readline())
        return(temperature)
        # PROTECTED REGION END #    //  CryoCon32.TemperatureA_read

    def read_SetPoint(self):
        # PROTECTED REGION ID(CryoCon32.SetPoint_read) ENABLED START #
        self.ser.write("LOOP 1:SETPT?\n")
        temperature=float(self.ser.readline()[:-2]) # Remove \n and units (assume we are in K!)
        return(temperature)
        # PROTECTED REGION END #    //  CryoCon32.SetPoint_read

    def write_SetPoint(self, value):
        # PROTECTED REGION ID(CryoCon32.SetPoint_write) ENABLED START #
        self.ser.write("LOOP 1:SETPT %f \n"%(value))
        # PROTECTED REGION END #    //  CryoCon32.SetPoint_write

    def read_TemperatureB(self):
        # PROTECTED REGION ID(CryoCon32.TemperatureB_read) ENABLED START #
        self.ser.write("INPUT? B\n")
        temperature=float(self.ser.readline())
        return(temperature)
        # PROTECTED REGION END #    //  CryoCon32.TemperatureB_read

    def read_HeaterLevel(self):
        # PROTECTED REGION ID(CryoCon32.HeaterLevel_read) ENABLED START #
        self.ser.write("LOOP 1:RANGE?\n")
        res=self.ser.readline()
        if(res[:-1]=="LOW"):
            return 0
        elif (res[:-1]=="MID"):
            return 1
        else:
            return 2
        # PROTECTED REGION END #    //  CryoCon32.HeaterLevel_read

    def write_HeaterLevel(self, value):
        # PROTECTED REGION ID(CryoCon32.HeaterLevel_write) ENABLED START #
        if (value==0):
            self.ser.write("LOOP 1:RANGE LOW\n")
        elif (value==1):
            self.ser.write("LOOP 1:RANGE MID\n")
        elif (value==2):
            self.ser.write("LOOP 1:RANGE HI\n")
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
        self.ser.write("CONTROL ON\n")
        self.set_state(PyTango.DevState.ON)
        pass
        # PROTECTED REGION END #    //  CryoCon32.On

    @command(
    )
    @DebugIt()
    def Off(self):
        # PROTECTED REGION ID(CryoCon32.Off) ENABLED START #
        self.ser.write("STOP\n")
        self.set_state(PyTango.DevState.OFF)
        pass
        # PROTECTED REGION END #    //  CryoCon32.Off

    @command(
    dtype_in='str', 
    )
    @DebugIt()
    def SendCmd(self, argin):
        # PROTECTED REGION ID(CryoCon32.SendCmd) ENABLED START #
        self.ser.write(argin+"\n")
        return ""
        # PROTECTED REGION END #    //  CryoCon32.SendCmd

    @command(
    dtype_in='str', 
    dtype_out='str', 
    )
    @DebugIt()
    def SendQuery(self, argin):
        # PROTECTED REGION ID(CryoCon32.SendQuery) ENABLED START #
        self.ser.write(argin+"\n")
        return self.ser.readline()
        # PROTECTED REGION END #    //  CryoCon32.SendQuery

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(CryoCon32.main) ENABLED START #
    return run((CryoCon32,), args=args, **kwargs)
    # PROTECTED REGION END #    //  CryoCon32.main

if __name__ == '__main__':
    main()
