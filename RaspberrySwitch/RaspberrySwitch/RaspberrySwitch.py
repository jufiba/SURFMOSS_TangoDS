# -*- coding: utf-8 -*-
#
# This file is part of the RaspberrySwitch project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" RaspberrySwitch

Read a switch connected to one of the GPIO pins.
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
# PROTECTED REGION ID(RaspberrySwitch.additionnal_import) ENABLED START #
import RPi.GPIO as GPIO
# PROTECTED REGION END #    //  RaspberrySwitch.additionnal_import

__all__ = ["RaspberrySwitch", "main"]


class RaspberrySwitch(Device):
    """
    Read a switch connected to one of the GPIO pins.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(RaspberrySwitch.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  RaspberrySwitch.class_variable

    # -----------------
    # Device Properties
    # -----------------

    GPIOport = device_property(
        dtype='uint16',
    )

    PullUPorDOWN = device_property(
        dtype='bool',
    )

    Sense = device_property(
        dtype='bool', default_value=True
    )

    # ----------
    # Attributes
    # ----------

    Switch = attribute(
        dtype='bool',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(RaspberrySwitch.init_device) ENABLED START #
        GPIO.setmode(GPIO.BCM)
        if (self.PullUPorDOWN==True):
            GPIO.setup(self.GPIOport, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        else:
           GPIO.setup(self.GPIOport, GPIO.IN, pull_up_down=GPIO.PUD_DOWN) 
        # PROTECTED REGION END #    //  RaspberrySwitch.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(RaspberrySwitch.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  RaspberrySwitch.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(RaspberrySwitch.delete_device) ENABLED START #
        pass
        # PROTECTED REGION END #    //  RaspberrySwitch.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Switch(self):
        # PROTECTED REGION ID(RaspberrySwitch.Switch_read) ENABLED START #
        reading=GPIO.input(self.GPIOport)
        if (reading):
	    if (self.Sense):
            	self.set_state(PyTango.DevState.ON)
            	return True
	    else:
            	self.set_state(PyTango.DevState.OFF)
            	return False
        else:
	    if (self.Sense):
            	self.set_state(PyTango.DevState.OFF)
            	return False
	    else:
            	self.set_state(PyTango.DevState.ON)
            	return True
        # PROTECTED REGION END #    //  RaspberrySwitch.Switch_read


    # --------
    # Commands
    # --------

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(RaspberrySwitch.main) ENABLED START #
    return run((RaspberrySwitch,), args=args, **kwargs)
    # PROTECTED REGION END #    //  RaspberrySwitch.main

if __name__ == '__main__':
    main()
