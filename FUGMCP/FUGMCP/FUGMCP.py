# -*- coding: utf-8 -*-
#
# This file is part of the FUGMCP project
#
# GPL 2
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" 

Device server for the HV power supply MCP 140-1250 (1250V, 100mA). It has a USB module for digital interfacing, Probus V.
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
# PROTECTED REGION ID(FUGMCP.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  FUGMCP.additionnal_import

__all__ = ["FUGMCP", "main"]


class FUGMCP(Device):
    """
    Device server for the HV power supply MCP 140-1250 (1250V, 100mA). It has a USB module for digital interfacing, Probus V.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(FUGMCP.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  FUGMCP.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str', default_value="/dev/ttyUSB0"
    )

    Speed = device_property(
        dtype='int', default_value=625000
    )

    # ----------
    # Attributes
    # ----------

    Voltage = attribute(
        dtype='double',
        label="Voltage",
        unit="V",
        format="%5.1f",
        max_value=1250,
        min_value=0,
    )

    Current = attribute(
        dtype='double',
        label="Current",
        unit="A",
        format="%6.4f",
        max_value=0.100,
        min_value=0,
    )

    Power = attribute(
        dtype='double',
        label="Power",
        unit="W",
        format="%5.1f",
    )

    SetVoltage = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        unit="V",
        format="%5.1f",
        max_value=1250,
        min_value=0,
    )

    SetCurrent = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        label="SetCurrent",
        unit="A",
        format="%6.4f",
        max_value=100,
        min_value=0,
    )

    Identification = attribute(
        dtype='str',
        display_level=DispLevel.EXPERT,
    )

    CC = attribute(
        dtype='bool',
    )

    CV = attribute(
        dtype='bool',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(FUGMCP.init_device) ENABLED START #
        try:
            self.ser=serial.Serial(port=self.SerialPort,baudrate=self.Speed,bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,stopbits=1,timeout=0.5)
            self.ser.write(bytes("*IDN?\n","ascii"))
            self.identification=self.ser.readline()
        except:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Can't connect to FUG MCP")
            self.debug_stream("Can't connect to FUG MCP")
            return
        if  (self.identification[0:16]!=bytes("FUG HCP 140-1250","ascii") and self.identification[0:15]!=bytes("FUG MCP140-1250","ascii")):
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("I do not find a FUG MCP on the serial port")
            self.debug_stream("I do not find a FUG MCP on the serial port")
            return
        self.set_status("Connected to FUG MCP")
        self.debug_stream("Connected to FUG MCP")
        self.ser.write(bytes(">BON?\n","ascii"))
        resp=self.ser.readline()
        if (resp[:-1]==bytes("BON:1","ascii")):
            self.set_state(PyTango.DevState.ON)
        else:
            self.set_state(PyTango.DevState.OFF)        
        # PROTECTED REGION END #    //  FUGMCP.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(FUGMCP.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  FUGMCP.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(FUGMCP.delete_device) ENABLED START #
        pass
        # PROTECTED REGION END #    //  FUGMCP.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Voltage(self):
        # PROTECTED REGION ID(FUGMCP.Voltage_read) ENABLED START #
        self.ser.write(bytes(">M0 ?\n","ascii"))
        resp=self.ser.readline()
        v=float(resp[3:-1])
        return(v)
        # PROTECTED REGION END #    //  FUGMCP.Voltage_read

    def read_Current(self):
        # PROTECTED REGION ID(FUGMCP.Current_read) ENABLED START #
        self.ser.write(bytes(">M1 ?\n","ascii"))
        resp=self.ser.readline()
        i=float(resp[3:-1])
        return(i)
        # PROTECTED REGION END #    //  FUGMCP.Current_read

    def read_Power(self):
        # PROTECTED REGION ID(FUGMCP.Power_read) ENABLED START #
        self.ser.write(bytes(">M0 ?\n","ascii"))
        resp=self.ser.readline()
        v=float(resp[3:-1])
        self.ser.write(bytes(">M1 ?\n","ascii"))
        resp=self.ser.readline()
        i=float(resp[3:-1])
        return(v*i)
        # PROTECTED REGION END #    //  FUGMCP.Power_read

    def read_SetVoltage(self):
        # PROTECTED REGION ID(FUGMCP.SetVoltage_read) ENABLED START #
        self.ser.write(bytes(">S0 ?\n","ascii"))
        resp=self.ser.readline()
        v=float(resp[3:-1])
        return(v)
        # PROTECTED REGION END #    //  FUGMCP.SetVoltage_read

    def write_SetVoltage(self, value):
        # PROTECTED REGION ID(FUGMCP.SetVoltage_write) ENABLED START #
        self.ser.write(bytes(">S0 %f\n"%value,"ascii"))
        resp=self.ser.readline()
        if (resp[:-1]!=bytes("E0","ascii")):
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Error writing SetVoltage from FUG MCP %s"%resp[:-1])
            self.debug_stream("Error writing SetVoltage from FUG MCP %s"%resp[:-1])
        return
        # PROTECTED REGION END #    //  FUGMCP.SetVoltage_write

    def read_SetCurrent(self):
        # PROTECTED REGION ID(FUGMCP.SetCurrent_read) ENABLED START #
        self.ser.write(bytes(">S1 ?\n","ascii"))
        resp=self.ser.readline()
        i=float(resp[3:-1])
        return(i)
        # PROTECTED REGION END #    //  FUGMCP.SetCurrent_read

    def write_SetCurrent(self, value):
        # PROTECTED REGION ID(FUGMCP.SetCurrent_write) ENABLED START #
        self.ser.write(bytes(">S1 %f\n"%value,"ascii"))
        resp=self.ser.readline()
        if (resp[:-1]!=bytes("E0","ascii")):
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Error writing SetCurret from FUG MCP %s"%resp[:-1])
            self.debug_stream("Error writing SetCurrent from FUG MCP %s"%resp[:-1])
        return
        # PROTECTED REGION END #    //  FUGMCP.SetCurrent_write

    def read_Identification(self):
        # PROTECTED REGION ID(FUGMCP.Identification_read) ENABLED START #
        return(self.identification)
        # PROTECTED REGION END #    //  FUGMCP.Identification_read

    def read_CC(self):
        # PROTECTED REGION ID(FUGMCP.CC_read) ENABLED START #
        self.ser.write(bytes(">DIR ?\n","ascii"))
        resp=self.ser.readline()
        if (resp[:-1]==bytes("DIR:1","ascii")):
            return(True)
        else:
            return(False)
        # PROTECTED REGION END #    //  FUGMCP.CC_read

    def read_CV(self):
        # PROTECTED REGION ID(FUGMCP.CV_read) ENABLED START #
        self.ser.write(bytes(">DVR ?\n","ascii"))
        resp=self.ser.readline()
        if (resp[:-1]==bytes("DVR:1","ascii")):
            return(True)
        else:
            return(False)
        # PROTECTED REGION END #    //  FUGMCP.CV_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def OutputOn(self):
        # PROTECTED REGION ID(FUGMCP.OutputOn) ENABLED START #
        self.ser.write(bytes(">BON 1\n","ascii"))
        resp=self.ser.readline()
        if (resp[:-1]!=bytes("E0","ascii")):
                self.set_state(PyTango.DevState.FAULT)
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  FUGMCP.OutputOn

    @command(
    )
    @DebugIt()
    def OutputOff(self):
        # PROTECTED REGION ID(FUGMCP.OutputOff) ENABLED START #
        self.ser.write(bytes(">BON 0\n","ascii"))
        resp=self.ser.readline()
        if (resp[:-1]!=bytes("E0","ascii")):
            self.set_state(PyTango.DevState.FAULT)
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  FUGMCP.OutputOff

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def sendCommand(self, argin):
        # PROTECTED REGION ID(FUGMCP.sendCommand) ENABLED START #
        self.ser.write(bytes(argin+"\n","ascii"))
        result=self.ser.readline()
        return(result)
        # PROTECTED REGION END #    //  FUGMCP.sendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(FUGMCP.main) ENABLED START #
    return run((FUGMCP,), args=args, **kwargs)
    # PROTECTED REGION END #    //  FUGMCP.main

if __name__ == '__main__':
    main()
