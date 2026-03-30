# -*- coding: utf-8 -*-
#
# This file is part of the SpecsXRC1000 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" SpecsXRC1000

Device server for reading the status of the XRC1000 X-ray gun electronics.
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
# PROTECTED REGION ID(SpecsXRC1000.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  SpecsXRC1000.additionnal_import

__all__ = ["SpecsXRC1000", "main"]


class SpecsXRC1000(Device):
    """
    Device server for reading the status of the XRC1000 X-ray gun electronics.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(SpecsXRC1000.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  SpecsXRC1000.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str', default_value="/dev/ttyUSB1"
    )

    # ----------
    # Attributes
    # ----------

    Power = attribute(
        dtype='double',
    )

    Operation = attribute(
        dtype='DevEnum',
        enum_labels=["off", "cooling on", "preheating", "anodo voltage", "on", ],
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(SpecsXRC1000.init_device) ENABLED START #
        self.ser=serial.Serial(self.SerialPort,baudrate=9600,bytesize=8,parity="N",stopbits=1,timeout=0.5)
        try:
            self.ser.flush()
            self.ser.write("SERNO ?\n")
            resp=self.ser.readline()[:-1]
            if (resp==">SERNO:000001D4B53828"):
                self.set_status("Connected to our Specs XRC1000")
                self.debug_stream("Connected to our Specs XRC1000")
        except:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Can't connect to Specs XRC1000")
            self.debug_stream("Can't connect to Specs XRC1000")
            return
        self.ser.write("OPE ?\n")
        resp=self.ser.readline()
        o=int(resp[10])
        if (o==0):
            self.set_state(PyTango.DevState.OFF)
        elif (o==4):
            self.set_state(PyTango.DevState.ON)
        else:
            self.set_state(PyTango.DevState.MOVING)
        # PROTECTED REGION END #    //  SpecsXRC1000.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(SpecsXRC1000.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  SpecsXRC1000.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(SpecsXRC1000.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  SpecsXRC1000.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Power(self):
        # PROTECTED REGION ID(SpecsXRC1000.Power_read) ENABLED START #
        self.ser.write("PAN ?\n")
        resp=float(self.ser.readline()[6:])
        return resp
        # PROTECTED REGION END #    //  SpecsXRC1000.Power_read

    def read_Operation(self):
        # PROTECTED REGION ID(SpecsXRC1000.Operation_read) ENABLED START #
        self.ser.write("OPE ?\n")
        resp=self.ser.readline()
        o=int(resp[10])
        if (o==0):
            self.set_state(PyTango.DevState.OFF)
        elif (o==4):
            self.set_state(PyTango.DevState.ON)
        else:
            self.set_state(PyTango.DevState.MOVING)
        return o
        # PROTECTED REGION END #    //  SpecsXRC1000.Operation_read


    # --------
    # Commands
    # --------

    @command(
    dtype_in='str', 
    dtype_out='str', 
    )
    @DebugIt()
    def SendCommand(self, argin):
        # PROTECTED REGION ID(SpecsXRC1000.SendCommand) ENABLED START #
        self.ser.write(argin+"\n")
        resp=self.ser.readline()
        return resp
        # PROTECTED REGION END #    //  SpecsXRC1000.SendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(SpecsXRC1000.main) ENABLED START #
    return run((SpecsXRC1000,), args=args, **kwargs)
    # PROTECTED REGION END #    //  SpecsXRC1000.main

if __name__ == '__main__':
    main()
