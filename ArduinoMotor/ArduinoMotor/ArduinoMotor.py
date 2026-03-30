# -*- coding: utf-8 -*-
#
# This file is part of the ArduinoMotor project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" ArduinoMotor

Custom server for an Arduino driving a motor.
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
# PROTECTED REGION ID(ArduinoMotor.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  ArduinoMotor.additionnal_import

__all__ = ["ArduinoMotor", "main"]


class ArduinoMotor(Device):
    """
    Custom server for an Arduino driving a motor.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(ArduinoMotor.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  ArduinoMotor.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str', default_value="/dev/ttyUSB0"
    )

    # ----------
    # Attributes
    # ----------

    Position = attribute(
        dtype='uint',
    )

    Info = attribute(
        dtype='str',
    )

    Mode = attribute(
        dtype='str',
    )

    Version = attribute(
        dtype='str',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(ArduinoMotor.init_device) ENABLED START #
        self.ser=serial.Serial(self.SerialPort,baudrate=9600,bytesize=8,parity="N",stopbits=1,timeout=1)
        #self.ser=serial.Serial(self.SerialPort,baudrate=9600)
        #except:
            #self.set_state(PyTango.DevState.FAULT)
            #self.set_status("Can't connect to ArduinoMotor")
            #self.debug_stream("Can't connect to ArduinoMotor")
            #return
        self.set_status("Connected to Arduino")
        self.debug_stream("Connected to Arduino")
        for i in range(0,10):
            self.ser.write(bytes("IDN?\n","ascii"))
            b=self.ser.readline()
            print(b)
        if (b[0:16]==bytes("Motor Sputtering","ascii")):
            self.set_status("Connected to %s"%b)
            self.set_state(PyTango.DevState.ON)
        else:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("ArduinoMotor IDN? returned %s"%b)
        for i in range(0,4):
            print(self.ser.readline())
        # PROTECTED REGION END #    //  ArduinoMotor.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(ArduinoMotor.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  ArduinoMotor.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(ArduinoMotor.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  ArduinoMotor.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Position(self):
        # PROTECTED REGION ID(ArduinoMotor.Position_read) ENABLED START #
        self.ser.write(bytes("POS?\n","ascii"))
        res=self.ser.readline()
        return (int(res))
        # PROTECTED REGION END #    //  ArduinoMotor.Position_read

    def read_Info(self):
        # PROTECTED REGION ID(ArduinoMotor.Info_read) ENABLED START #
        self.ser.write(bytes("STAT?\n","ascii"))
        res=self.ser.readline()
        return (res)
        # PROTECTED REGION END #    //  ArduinoMotor.Info_read

    def read_Mode(self):
        # PROTECTED REGION ID(ArduinoMotor.Mode_read) ENABLED START #
        self.ser.write(bytes("MODO?\n","ascii"))
        res=self.ser.readline()
        return (res)
        # PROTECTED REGION END #    //  ArduinoMotor.Mode_read

    def read_Version(self):
        # PROTECTED REGION ID(ArduinoMotor.Version_read) ENABLED START #
        self.ser.write(bytes("IDN?\n","ascii"))
        res=self.ser.readline()
        return (res)
        # PROTECTED REGION END #    //  ArduinoMotor.Version_read


    # --------
    # Commands
    # --------

    @command(
    dtype_in='uint', 
    )
    @DebugIt()
    def MoveSteps(self, argin):
        # PROTECTED REGION ID(ArduinoMotor.MoveSteps) ENABLED START #
        self.ser.write(bytes("MOVE %d\n"%argin,"ascii"))
        # PROTECTED REGION END #    //  ArduinoMotor.MoveSteps

    @command(
    )
    @DebugIt()
    def Calibrate(self):
        # PROTECTED REGION ID(ArduinoMotor.Calibrate) ENABLED START #
        self.ser.write(bytes("CAL\n","ascii"))
        # PROTECTED REGION END #    //  ArduinoMotor.Calibrate

    @command(
    dtype_in='str', 
    )
    @DebugIt()
    def MoveToPos(self, argin):
        # PROTECTED REGION ID(ArduinoMotor.MoveToPos) ENABLED START #
        self.ser.write(bytes("MOVEP %s\n"%argin,"ascii"))
        # PROTECTED REGION END #    //  ArduinoMotor.MoveToPos

    @command(
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(ArduinoMotor.Stop) ENABLED START #
        self.ser.write(bytes("STOP\n","ascii"))
        # PROTECTED REGION END #    //  ArduinoMotor.Stop

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(ArduinoMotor.main) ENABLED START #
    return run((ArduinoMotor,), args=args, **kwargs)
    # PROTECTED REGION END #    //  ArduinoMotor.main

if __name__ == '__main__':
    main()
