# -*- coding: utf-8 -*-
#
# This file is part of the MKSGauge project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" MKSGauge Reader

This is a very simple reader for the PDR9000 unit with a 972B transducer.
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
# PROTECTED REGION ID(MKSGauge.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  MKSGauge.additionnal_import

__all__ = ["MKSGauge", "main"]


class MKSGauge(Device):
    """
    This is a very simple reader for the PDR9000 unit with a 972B transducer.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(MKSGauge.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  MKSGauge.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str',
        mandatory=True
    )

    Speed = device_property(
        dtype='uint',
        mandatory=True
    )

    # ----------
    # Attributes
    # ----------

    Pressure = attribute(
        dtype='double',
        label="Pressure",
        unit="mbar",
        standard_unit="mbar",
        display_unit="mbar",
        format="%4.2e",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(MKSGauge.init_device) ENABLED START #
        self.ser=serial.Serial(self.SerialPort,baudrate=self.Speed,bytesize=8,parity="N",stopbits=1,timeout=0.5)
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  MKSGauge.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(MKSGauge.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  MKSGauge.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(MKSGauge.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  MKSGauge.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Pressure(self):
        # PROTECTED REGION ID(MKSGauge.Pressure_read) ENABLED START #
        self.ser.write("@254PR4?;FF")
        a=self.ser.read_until(terminator=";FF")
        if (a[0:7]=="@253ACK"):
            return float(a[7:15])
        return 9999
        # PROTECTED REGION END #    //  MKSGauge.Pressure_read


    # --------
    # Commands
    # --------

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def sendCommand(self, argin):
        # PROTECTED REGION ID(MKSGauge.sendCommand) ENABLED START #
        self.ser.write(argin+";FF")
        return self.ser.read_until(terminator=";FF")
        # PROTECTED REGION END #    //  MKSGauge.sendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(MKSGauge.main) ENABLED START #
    return run((MKSGauge,), args=args, **kwargs)
    # PROTECTED REGION END #    //  MKSGauge.main

if __name__ == '__main__':
    main()
