# -*- coding: utf-8 -*-
#
# This file is part of the AMLPGC1 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" AMLPGC1

Device server for AML PGC1.
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
# PROTECTED REGION ID(AMLPGC1.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  AMLPGC1.additionnal_import

__all__ = ["AMLPGC1", "main"]


class AMLPGC1(Device):
    """
    Device server for AML PGC1.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(AMLPGC1.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  AMLPGC1.class_variable

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
        format="%.1e",
    )

    Remote = attribute(
        dtype='bool',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(AMLPGC1.init_device) ENABLED START #
        try:
            self.ser=serial.Serial(self.SerialPort,baudrate=9600,bytesize=8,parity="N",stopbits=1,timeout=0.5)
            self.ser.write("*S0\r\n")
            resp=self.ser.readline()
        except:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Can't connect to AMLPGC1")
            self.debug_stream("Can't connect to AMLPGC1")
            return
        self.set_status("Connected to AMLPGC1")
        self.debug_stream("Connected to AMLPGC1")
        if (ord(resp[7])&0b0001==0b00001):
            self.set_state(PyTango.DevState.ON)
        else:
            self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  AMLPGC1.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(AMLPGC1.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  AMLPGC1.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(AMLPGC1.delete_device) ENABLED START #
        self.ser.write("*P0\r\n")
        a=self.ser.readline()
        if (ord(a[0])&0b10000==0b10000):
            self.ser.write("*R0\r\n")
            resp=self.ser.readline()
        self.ser.close()
        # PROTECTED REGION END #    //  AMLPGC1.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Pressure(self):
        # PROTECTED REGION ID(AMLPGC1.Pressure_read) ENABLED START #
        self.ser.write("*S0\r\n")
        self.ser.inWaiting()
        a=self.ser.readline()
        pressure=(a[9:].split(",")[0])
        return float(pressure)
        # PROTECTED REGION END #    //  AMLPGC1.Pressure_read

    def read_Remote(self):
        # PROTECTED REGION ID(AMLPGC1.Remote_read) ENABLED START #
        self.ser.write("*P0\r\n")
        a=self.ser.readline()
        if (ord(a[0])&0b10000==0b10000):
            return True
        else:
            return False
        # PROTECTED REGION END #    //  AMLPGC1.Remote_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def Start(self):
        # PROTECTED REGION ID(AMLPGC1.Start) ENABLED START #
        self.ser.write("*i03\r\n")
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  AMLPGC1.Start

    @command(
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(AMLPGC1.Stop) ENABLED START #
        self.ser.write("*o0\r\n")
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  AMLPGC1.Stop

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def setCommand(self, argin):
        # PROTECTED REGION ID(AMLPGC1.setCommand) ENABLED START #
        self.ser.write("*"+argin+"\r\n")
        return self.ser.readline()
        # PROTECTED REGION END #    //  AMLPGC1.setCommand

    @command(
    )
    @DebugIt()
    def SetLocal(self):
        # PROTECTED REGION ID(AMLPGC1.SetLocal) ENABLED START #
        self.ser.write("*R0\r\n")
        resp=self.ser.readline()
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  AMLPGC1.SetLocal

    @command(
    )
    @DebugIt()
    def SetRemote(self):
        # PROTECTED REGION ID(AMLPGC1.SetRemote) ENABLED START #
        self.ser.write("*C0\r\n") # Set remote mode
        resp=self.ser.readline()
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  AMLPGC1.SetRemote

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(AMLPGC1.main) ENABLED START #
    return run((AMLPGC1,), args=args, **kwargs)
    # PROTECTED REGION END #    //  AMLPGC1.main

if __name__ == '__main__':
    main()
