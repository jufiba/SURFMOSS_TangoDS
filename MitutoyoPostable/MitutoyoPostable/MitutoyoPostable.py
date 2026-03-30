# -*- coding: utf-8 -*-
#
# This file is part of the MitutoyoPostable project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" MitutoyoPostable

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
# PROTECTED REGION ID(MitutoyoPostable.additionnal_import) ENABLED START #
import serial
from threading import Thread
import time

class ControlThread(Thread):
    
    def __init__ (self, ds):
        Thread.__init__(self)
        self.ds = ds
 
    def run(self):        
        while(self.ds.running):
            self.ds.ser.write("*POS?\n")
            self.ds.ser.inWaiting()
            pos=self.ds.ser.readline()
            while ("ERR" in pos):
                self.ds.ser.write("*RST\n")
                self.ds.ser.write("*POS?\n")
                pos=self.ds.ser.readline()
            self.ds.pos=pos
            time.sleep(2)
        
# PROTECTED REGION END #    //  MitutoyoPostable.additionnal_import

__all__ = ["MitutoyoPostable", "main"]


class MitutoyoPostable(Device):
    """
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(MitutoyoPostable.class_variable) ENABLED START #
    pos="( 0.0 , 0.0)"
    # PROTECTED REGION END #    //  MitutoyoPostable.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str',
    )

    # ----------
    # Attributes
    # ----------

    Position = attribute(
        dtype='str',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(MitutoyoPostable.init_device) ENABLED START #
        self.ser=serial.Serial(self.SerialPort,baudrate=9600,bytesize=8,parity="N",stopbits=1,timeout=0.5)
        try:
            self.ser.write("*POS?\n")
            idn=self.ser.readline()
            self.debug_stream(idn)
        except:
                self.set_state(PyTango.DevState.FAULT)
                self.set_status("Can't connect to Mitutoyo")
                self.debug_stream("Can't connect to Mitutoyo")
                return
        self.set_status("Connected to Mitutoyo")
        self.debug_stream("Connected to Mitutoyo")
        self.set_state(PyTango.DevState.ON)
        self.running=True
        ctrlloop = ControlThread(self)
        ctrlloop.start()
        # PROTECTED REGION END #    //  MitutoyoPostable.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(MitutoyoPostable.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  MitutoyoPostable.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(MitutoyoPostable.delete_device) ENABLED START #
        self.ser.close()
        self.running=False
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  MitutoyoPostable.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Position(self):
        # PROTECTED REGION ID(MitutoyoPostable.Position_read) ENABLED START #
        return (self.pos)
        # PROTECTED REGION END #    //  MitutoyoPostable.Position_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def Reset(self):
        # PROTECTED REGION ID(MitutoyoPostable.Reset) ENABLED START #
        self.ser.write("*RST\n");
        # Dangerous!! Now there is a thread running at the same time, this will collide with it. 
        # PROTECTED REGION END #    //  MitutoyoPostable.Reset

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def SendCommand(self, argin):
        # PROTECTED REGION ID(MitutoyoPostable.SendCommand) ENABLED START #
        self.ser.write(argin)
        reading=self.ser.readline()
         # Dangerous!! Now there is a thread running at the same time, this will collide with it. 
        return reading
        # PROTECTED REGION END #    //  MitutoyoPostable.SendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(MitutoyoPostable.main) ENABLED START #
    return run((MitutoyoPostable,), args=args, **kwargs)
    # PROTECTED REGION END #    //  MitutoyoPostable.main

if __name__ == '__main__':
    main()
