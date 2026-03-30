# -*- coding: utf-8 -*-
#
# This file is part of the Hygrometer project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" Hydrometer

DS for reading the data from an Arduino connected to YL-69/YL-38 sensors.
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
# PROTECTED REGION ID(Hygrometer.additionnal_import) ENABLED START #
import serial
from threading import Thread
import time

class ControlThread(Thread):
    
    def __init__ (self, ds):
        Thread.__init__(self)
        self.ds = ds
 
    def run(self):        
        while(self.ds.running):
            self.ds.ser.write(bytes("read","ascii"))
            self.ds.ser.inWaiting()
            resp=self.ds.ser.readline()
            self.ds.h=float(resp)
            time.sleep(5)
# PROTECTED REGION END #    //  Hygrometer.additionnal_import

__all__ = ["Hygrometer", "main"]


class Hygrometer(Device, metaclass = DeviceMeta):
    """
    DS for reading the data from an Arduino connected to YL-69/YL-38 sensors.
    """
    
    # PROTECTED REGION ID(Hygrometer.class_variable) ENABLED START #
    h=0
    running=True
    # PROTECTED REGION END #    //  Hygrometer.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str', default_value="/dev/ttyUSB0"
    )

    # ----------
    # Attributes
    # ----------

    Humidity = attribute(
        dtype='double',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(Hygrometer.init_device) ENABLED START #
        self.ser=serial.Serial(self.SerialPort,baudrate=9600,timeout=5.5)
        try:
            for i in range(0,2):
                self.ser.flushInput()
                self.ser.write(bytes("id","ascii"))
                self.ser.inWaiting()
                resp=self.ser.readline()
        except:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Can't connect to Hygrometer")
            self.debug_stream("Can't connect to Hygrometer")
            return
        self.set_status("Connected to Arduino Hygrometer")
        self.debug_stream("Connected to Arduino Hygrometer")
        if (resp==bytes("Flood sensor above XPS\r\n","ascii")):
            self.set_state(PyTango.DevState.ON)
            self.running=True
            ctrlloop = ControlThread(self)
            ctrlloop.start()
        else:
            self.set_state(PyTango.DevState.FAULT)
        
        # PROTECTED REGION END #    //  Hygrometer.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(Hygrometer.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  Hygrometer.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(Hygrometer.delete_device) ENABLED START #
        self.ser.close()
        self.running=False
        # PROTECTED REGION END #    //  Hygrometer.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Humidity(self):
        # PROTECTED REGION ID(Hygrometer.Humidity_read) ENABLED START #
        return(self.h)
        # PROTECTED REGION END #    //  Hygrometer.Humidity_read


    # --------
    # Commands
    # --------

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(Hygrometer.main) ENABLED START #
    return run((Hygrometer,), args=args, **kwargs)
    # PROTECTED REGION END #    //  Hygrometer.main

if __name__ == '__main__':
    main()
