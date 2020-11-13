# -*- coding: utf-8 -*-
#
# This file is part of the RaspberryButton project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" RaspberryButton

A device to turn on for a second one of the lines of the GPIO, used to drive a relay for turning on an off equipment.
"""

# PyTango imports
import PyTango
from PyTango import DebugIt
from PyTango.server import run
from PyTango.server import Device, DeviceMeta
from PyTango.server import command
from PyTango import AttrQuality, DispLevel, DevState
from PyTango import AttrWriteType, PipeWriteType
# Additional import
# PROTECTED REGION ID(RaspberryButton.additionnal_import) ENABLED START #
import RPi.GPIO as GPIO
import time
# PROTECTED REGION END #    //  RaspberryButton.additionnal_import

__all__ = ["RaspberryButton", "main"]


class RaspberryButton(Device):
    """
    A device to turn on for a second one of the lines of the GPIO, used to drive a relay for turning on an off equipment.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(RaspberryButton.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  RaspberryButton.class_variable

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(RaspberryButton.init_device) ENABLED START #
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(17, GPIO.OUT)
        GPIO.setup(22, GPIO.OUT)
        GPIO.output(17,1)
        GPIO.output(22,1)
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  RaspberryButton.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(RaspberryButton.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  RaspberryButton.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(RaspberryButton.delete_device) ENABLED START #
        pass
        # PROTECTED REGION END #    //  RaspberryButton.delete_device


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def DiffusionPump(self):
        # PROTECTED REGION ID(RaspberryButton.DiffusionPump) ENABLED START #
        GPIO.output(17,1)
        time.sleep(1)
        GPIO.output(17,0)
        time.sleep(1)
        GPIO.output(17,1)
        # PROTECTED REGION END #    //  RaspberryButton.DiffusionPump

    @command(
    )
    @DebugIt()
    def Compressor(self):
        # PROTECTED REGION ID(RaspberryButton.Compressor) ENABLED START #
        GPIO.output(22,1)
        time.sleep(1)
        GPIO.output(22,0)
        time.sleep(1)
        GPIO.output(22,1)
        # PROTECTED REGION END #    //  RaspberryButton.Compressor

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(RaspberryButton.main) ENABLED START #
    return run((RaspberryButton,), args=args, **kwargs)
    # PROTECTED REGION END #    //  RaspberryButton.main

if __name__ == '__main__':
    main()
