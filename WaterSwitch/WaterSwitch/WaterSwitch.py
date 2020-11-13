# -*- coding: utf-8 -*-
#
# This file is part of the WaterSwitch project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" 

Simple device server to detect wheter water is flowing in a cooling water sensor
"""

# PyTango imports
import PyTango
from PyTango import DebugIt
from PyTango.server import run
from PyTango.server import Device, DeviceMeta
from PyTango.server import attribute, command
from PyTango import AttrQuality, DispLevel, DevState
from PyTango import AttrWriteType, PipeWriteType
# Additional import
# PROTECTED REGION ID(WaterSwitch.additionnal_import) ENABLED START #
import RPi.GPIO as GPIO
# PROTECTED REGION END #    //  WaterSwitch.additionnal_import

__all__ = ["WaterSwitch", "main"]


class WaterSwitch(Device):
    """
    Simple device server to detect wheter water is flowing in a cooling water sensor
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(WaterSwitch.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  WaterSwitch.class_variable

    # ----------
    # Attributes
    # ----------

    WaterFlowing = attribute(
        dtype='bool',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(WaterSwitch.init_device) ENABLED START #
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(21, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        # PROTECTED REGION END #    //  WaterSwitch.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(WaterSwitch.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WaterSwitch.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(WaterSwitch.delete_device) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WaterSwitch.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_WaterFlowing(self):
        # PROTECTED REGION ID(WaterSwitch.WaterFlowing_read) ENABLED START #
        reading=GPIO.input(21)
        if (reading):
            self.set_state(PyTango.DevState.OFF)
            return False
        else:
            self.set_state(PyTango.DevState.ON)
            return True
        # PROTECTED REGION END #    //  WaterSwitch.WaterFlowing_read


    # --------
    # Commands
    # --------

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(WaterSwitch.main) ENABLED START #
    return run((WaterSwitch,), args=args, **kwargs)
    # PROTECTED REGION END #    //  WaterSwitch.main

if __name__ == '__main__':
    main()
