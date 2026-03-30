# -*- coding: utf-8 -*-
#
# This file is part of the Motor project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" 

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
# PROTECTED REGION ID(Motor.additionnal_import) ENABLED START #
import time
import RPi.GPIO as GPIO
from threading import Thread

class ControlThread(Thread):
    
    def __init__ (self, ds):
        Thread.__init__(self)
        self.ds = ds
 
    def run(self):        
        halfstep_left = [
            [1, 0, 0, 0],
            [1, 1, 0, 0],
            [0, 1, 0, 0],
            [0, 1, 1, 0],
            [0, 0, 1, 0],
            [0, 0, 1, 1],
            [0, 0, 0, 1],
            [1, 0, 0, 1],
        ]
        if self.ds.direction == 1:
            serie=range(0,8,1)
        else:
            serie=range(7,-1,-1)
        
        while(self.ds.RemainingSteps_count > 0):
            self.ds.RemainingSteps_count-=1
            for j in serie:
                  #if GPIO.input == False:
                  GPIO.output(self.ds.StepPins, halfstep_left[j])
                  time.sleep(self.ds.Delay)
        self.ds.set_state(PyTango.DevState.ON)
# PROTECTED REGION END #    //  Motor.additionnal_import

__all__ = ["Motor", "main"]


class Motor(Device,metaclass = DeviceMeta):
    """
    """
    # PROTECTED REGION ID(Motor.class_variable) ENABLED START #
    RemainingSteps_count= 0
    # PROTECTED REGION END #    //  Motor.class_variable

    # -----------------
    # Device Properties
    # -----------------

    Delay = device_property(
        dtype='double', default_value=0.4
    )

    Pins = device_property(
        dtype='str', default_value="26,22,4,17"
    )

    # ----------
    # Attributes
    # ----------

    Direction = attribute(
        dtype='DevEnum',
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        enum_labels=["CW", "CCW", ],
    )

    Steps = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        memorized=True,
    )

    RemainingSteps = attribute(
        dtype='uint16',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(Motor.init_device) ENABLED START #
        self.direction = 0
        self.steps = 10
        self.StepPins=[]
        GPIO.setmode(GPIO.BCM)
        self.set_state(PyTango.DevState.ON) 
        for i in self.Pins.split(","):
            self.StepPins.append(int(i))
        for pin in self.StepPins:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, False)
            GPIO.PWM(pin, 100)
        # PROTECTED REGION END #    //  Motor.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(Motor.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  Motor.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(Motor.delete_device) ENABLED START #
        GPIO.cleanup()
        # PROTECTED REGION END #    //  Motor.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Direction(self):
        # PROTECTED REGION ID(Motor.Direction_read) ENABLED START #
        return self.direction
        # PROTECTED REGION END #    //  Motor.Direction_read

    def write_Direction(self, value):
        # PROTECTED REGION ID(Motor.Direction_write) ENABLED START #
        self.direction = value
        # PROTECTED REGION END #    //  Motor.Direction_write

    def read_Steps(self):
        # PROTECTED REGION ID(Motor.Steps_read) ENABLED START #
        return self.steps
        # PROTECTED REGION END #    //  Motor.Steps_read

    def write_Steps(self, value):
        # PROTECTED REGION ID(Motor.Steps_write) ENABLED START #
        self.steps = value
        # PROTECTED REGION END #    //  Motor.Steps_write

    def read_RemainingSteps(self):
        # PROTECTED REGION ID(Motor.RemainingSteps_read) ENABLED START #
        return self.RemainingSteps_count
        # PROTECTED REGION END #    //  Motor.RemainingSteps_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def Move(self):
        # PROTECTED REGION ID(Motor.Move) ENABLED START #
        state=self.get_state()
        if (state==PyTango.DevState.MOVING): 
            return
        elif (state==PyTango.DevState.ON):
            self.RemainingSteps_count=self.steps
            ctrlloop = ControlThread(self)
            ctrlloop.start()
            self.set_state(PyTango.DevState.MOVING)
        return
        # PROTECTED REGION END #    //  Motor.Move

    @command(
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(Motor.Stop) ENABLED START #
        state=self.get_state()
        if (state==PyTango.DevState.MOVING):
            self.RemainingSteps_count=0
            return
        elif (state==PyTango.DevState.ON):
            return
        # PROTECTED REGION END #    //  Motor.Stop

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(Motor.main) ENABLED START #
    from PyTango.server import run
    return run((Motor,), args=args, **kwargs)
    # PROTECTED REGION END #    //  Motor.main

if __name__ == '__main__':
    main()
