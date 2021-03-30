# -*- coding: utf-8 -*-
#
# This file is part of the RaspberryButton project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" RaspberryButton

Simple interface to turn on and off a GPIO pin in a Raspberry PI.
"""

# PyTango imports
import PyTango
from PyTango import DebugIt
from PyTango.server import run
from PyTango.server import Device, DeviceMeta
from PyTango.server import command
from PyTango.server import device_property
from PyTango import AttrQuality, DispLevel, DevState
from PyTango import AttrWriteType, PipeWriteType
# Additional import
# PROTECTED REGION ID(RaspberryButton.additionnal_import) ENABLED START #
import RPi.GPIO as GPIO
# PROTECTED REGION END #    //  RaspberryButton.additionnal_import

__all__ = ["RaspberryButton", "main"]


class RaspberryButton(Device,metaclass=DeviceMeta):
    """
    Simple interface to turn on and off a GPIO pin in a Raspberry PI.
    """
    #__metaclass__ = DeviceMeta
    # PROTECTED REGION ID(RaspberryButton.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  RaspberryButton.class_variable

    # -----------------
    # Device Properties
    # -----------------

    Pin = device_property(
        dtype='uint16',
    )

    TrueHigh = device_property(
        dtype='bool',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(RaspberryButton.init_device) ENABLED START #
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.Pin, GPIO.OUT)
        if (self.TrueHigh==True):
            GPIO.output(self.Pin,0)
        else:
            GPIO.output(self.Pin,1)
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  RaspberryButton.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(RaspberryButton.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  RaspberryButton.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(RaspberryButton.delete_device) ENABLED START #
        GPIO.cleanup()
        # PROTECTED REGION END #    //  RaspberryButton.delete_device


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def On(self):
        # PROTECTED REGION ID(RaspberryButton.On) ENABLED START #
        if (self.TrueHigh==True):
            GPIO.output(self.Pin,1)
        else:
            GPIO.output(self.Pin,0)
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  RaspberryButton.On

    @command(
    )
    @DebugIt()
    def Off(self):
        # PROTECTED REGION ID(RaspberryButton.Off) ENABLED START #
        if (self.TrueHigh==True):
            GPIO.output(self.Pin,0)
        else:
            GPIO.output(self.Pin,1)
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  RaspberryButton.Off

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(RaspberryButton.main) ENABLED START #
    return run((RaspberryButton,), args=args, **kwargs)
    # PROTECTED REGION END #    //  RaspberryButton.main

if __name__ == '__main__':
    main()
