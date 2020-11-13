# -*- coding: utf-8 -*-
#
# This file is part of the VarianMultiGauge project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" VarianMultiGauge

Simple devicer server for the Varian Multigauge controller. Asumes it has a hot cathode gauge.
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
# PROTECTED REGION ID(VarianMultiGauge.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  VarianMultiGauge.additionnal_import

__all__ = ["VarianMultiGauge", "main"]


class VarianMultiGauge(Device):
    """
    Simple devicer server for the Varian Multigauge controller. Asumes it has a hot cathode gauge.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(VarianMultiGauge.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  VarianMultiGauge.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str',
    )

    Speed = device_property(
        dtype='uint16',
    )

    # ----------
    # Attributes
    # ----------

    Pressure_IG1 = attribute(
        dtype='double',
        unit="mbar",
        format="%.1e",
    )

    Pressure_IG2 = attribute(
        dtype='double',
        unit="mbar",
        format="%.1e",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(VarianMultiGauge.init_device) ENABLED START #
        try:
            self.ser=serial.Serial(self.SerialPort,baudrate=self.Speed,bytesize=8,parity="N",stopbits=1,timeout=1)
            self.ser.write("#0011\r") # Set units to mbar
            self.ser.inWaiting()
            resp=self.ser.readline()
            self.ser.write("#0032I1\r") # Check emission on IC1
            self.ser.inWaiting()
            resp=self.ser.readline()
        except:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Can't connect to Varian MultiGauge")
            self.debug_stream("Can't connect to Varian MultiGauge")
            return
        self.set_status("Connected to Varian MultiGauge")
        self.debug_stream("Connected to Varian MultiGauge")
        
        if (resp==">01\r"): # Only check first gauge to set device status
            self.set_state(PyTango.DevState.ON)
        else:
            self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  VarianMultiGauge.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(VarianMultiGauge.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  VarianMultiGauge.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(VarianMultiGauge.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  VarianMultiGauge.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Pressure_IG1(self):
        # PROTECTED REGION ID(VarianMultiGauge.Pressure_IG1_read) ENABLED START #
        self.ser.write("#0002I1\r")
        self.ser.inWaiting()
        a=self.ser.readline()
        return(float(a[1:]))
        # PROTECTED REGION END #    //  VarianMultiGauge.Pressure_IG1_read

    def read_Pressure_IG2(self):
        # PROTECTED REGION ID(VarianMultiGauge.Pressure_IG2_read) ENABLED START #
        self.ser.write("#0002I2\r")
        self.ser.inWaiting()
        a=self.ser.readline()
        return(float(a[1:]))
        # PROTECTED REGION END #    //  VarianMultiGauge.Pressure_IG2_read


    # --------
    # Commands
    # --------

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def SendCommand(self, argin):
        # PROTECTED REGION ID(VarianMultiGauge.SendCommand) ENABLED START #
        self.ser.write(argin+"\r")
        self.ser.inWaiting()
        res=self.ser.readline()
        return(res)
        # PROTECTED REGION END #    //  VarianMultiGauge.SendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(VarianMultiGauge.main) ENABLED START #
    return run((VarianMultiGauge,), args=args, **kwargs)
    # PROTECTED REGION END #    //  VarianMultiGauge.main

if __name__ == '__main__':
    main()
