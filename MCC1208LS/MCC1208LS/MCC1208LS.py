# -*- coding: utf-8 -*-
#
# This file is part of the MCC1208LS project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" MCC1208LS

Simple interface to the MCC 1208LS usb DAC/ADC box.
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
# PROTECTED REGION ID(MCC1208LS.additionnal_import) ENABLED START #
import usb_1208LS
# PROTECTED REGION END #    //  MCC1208LS.additionnal_import

__all__ = ["MCC1208LS", "main"]


class MCC1208LS(Device):
    """
    Simple interface to the MCC 1208LS usb DAC/ADC box.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(MCC1208LS.class_variable) ENABLED START #
    SelectGain=(usb_1208LS.usb_1208LS.BP_20_00V,usb_1208LS.usb_1208LS.BP_10_00V,usb_1208LS.usb_1208LS.BP_5_00V,usb_1208LS.usb_1208LS.BP_4_00V,usb_1208LS.usb_1208LS.BP_2_50V,usb_1208LS.usb_1208LS.BP_2_00V,usb_1208LS.usb_1208LS.BP_1_25V,usb_1208LS.usb_1208LS.BP_1_00V)
    # PROTECTED REGION END #    //  MCC1208LS.class_variable

    # -----------------
    # Device Properties
    # -----------------

    DAC0Scale = device_property(
        dtype='double', default_value=35.85
    )

    ADC0Scale = device_property(
        dtype='double', default_value=1.0
    )

    ADC1Scale = device_property(
        dtype='double', default_value=100.0
    )

    # ----------
    # Attributes
    # ----------

    DAC0 = attribute(
        dtype='double',
        access=AttrWriteType.WRITE,
        display_level=DispLevel.EXPERT,
    )

    ADC0 = attribute(
        dtype='double',
        format="%.2e",
    )

    ADC0Gain = attribute(
        dtype='char',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        doc="gain: 1/ 20V, 2/10V, 3/5V, 4/4V, 5/2.5V, 6/2.0V 7 /1.25V, 8/1.0V",
    )

    ADC1Gain = attribute(
        dtype='char',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
    )

    ADC1 = attribute(
        dtype='double',
        display_level=DispLevel.EXPERT,
        format="%.2e",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(MCC1208LS.init_device) ENABLED START #
        self.ubox=usb_1208LS.usb_1208LS()
        self.ADC0gain = usb_1208LS.usb_1208LS.BP_10_00V
        self.ADC1gain = usb_1208LS.usb_1208LS.BP_1_00V
        self.ADC0value= 2
        self.ADC1value= 8
        self.set_status("Connected to MCC1208LS")
        self.debug_stream("Connected to MCC1208LS")
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  MCC1208LS.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(MCC1208LS.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  MCC1208LS.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(MCC1208LS.delete_device) ENABLED START #
        pass
        # PROTECTED REGION END #    //  MCC1208LS.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def write_DAC0(self, value):
        # PROTECTED REGION ID(MCC1208LS.DAC0_write) ENABLED START #
        self.ubox.AOut(0,int(value*self.DAC0Scale))
        # PROTECTED REGION END #    //  MCC1208LS.DAC0_write

    def read_ADC0(self):
        # PROTECTED REGION ID(MCC1208LS.ADC0_read) ENABLED START #
        return (self.ADC0Scale*self.ubox.volts(self.ADC0gain,self.ubox.AIn(0,self.ADC0gain)))
        # PROTECTED REGION END #    //  MCC1208LS.ADC0_read

    def read_ADC0Gain(self):
        # PROTECTED REGION ID(MCC1208LS.ADC0Gain_read) ENABLED START #
        return self.ADC0value
        # PROTECTED REGION END #    //  MCC1208LS.ADC0Gain_read

    def write_ADC0Gain(self, value):
        # PROTECTED REGION ID(MCC1208LS.ADC0Gain_write) ENABLED START #        
        self.ADC0value= value
        self.ADC0gain=self.SelectGain[value-1]
        # PROTECTED REGION END #    //  MCC1208LS.ADC0Gain_write

    def read_ADC1Gain(self):
        # PROTECTED REGION ID(MCC1208LS.ADC1Gain_read) ENABLED START #
        return self.ADC1value
        # PROTECTED REGION END #    //  MCC1208LS.ADC1Gain_read

    def write_ADC1Gain(self, value):
        # PROTECTED REGION ID(MCC1208LS.ADC1Gain_write) ENABLED START #
        self.ADC1value= value
        self.ADC1gain=self.SelectGain[value-1]
        # PROTECTED REGION END #    //  MCC1208LS.ADC1Gain_write

    def read_ADC1(self):
        # PROTECTED REGION ID(MCC1208LS.ADC1_read) ENABLED START #
        return (self.ADC1Scale*self.ubox.volts(self.ADC1gain,self.ubox.AIn(1,self.ADC1gain)))
        # PROTECTED REGION END #    //  MCC1208LS.ADC1_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def Blink(self):
        # PROTECTED REGION ID(MCC1208LS.Blink) ENABLED START #
        self.ubox.Blink()
        # PROTECTED REGION END #    //  MCC1208LS.Blink

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(MCC1208LS.main) ENABLED START #
    return run((MCC1208LS,), args=args, **kwargs)
    # PROTECTED REGION END #    //  MCC1208LS.main

if __name__ == '__main__':
    main()
