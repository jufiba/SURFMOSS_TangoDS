# -*- coding: utf-8 -*-
#
# This file is part of the TempSensorDS18B20 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" TempSensorDS18B20

Device server to read the temperature in a Raspberry PI with a DS18B20 sensor.

It needs (if using GPIO pin 4):
- the w1_gpio,w1_therm modules in /etc/modules
- set dtoverlay=w1-gpio,gpiopin=4 in /boot/config.txt&
- python3-w1termsensor module
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
# PROTECTED REGION ID(TempSensorDS18B20.additionnal_import) ENABLED START #
import RPi.GPIO as GPIO
import w1thermsensor

from threading import Thread
import time

class ControlThread(Thread):
    
    def __init__ (self, ds):
        Thread.__init__(self)
        self.ds = ds
 
    def run(self):        
        while(self.ds.running):
            temp=self.ds.sensor.get_temperature()
            self.ds.temp=temp
            time.sleep(5)
        
# PROTECTED REGION END #    //  TempSensorDS18B20.additionnal_import

__all__ = ["TempSensorDS18B20", "main"]


class TempSensorDS18B20(Device, metaclass=DeviceMeta):
    """
    Device server to read the temperature in a Raspberry PI with a DS18B20 sensor.

    It needs (if using GPIO pin 4):
    - the w1_gpio,w1_therm modules in /etc/modules
    - set dtoverlay=w1-gpio,gpiopin=4 in /boot/config.txt&
    - python3-w1termsensor module
    """
    # PROTECTED REGION ID(TempSensorDS18B20.class_variable) ENABLED START #
    temp=0.0
    # PROTECTED REGION END #    //  TempSensorDS18B20.class_variable

    # -----------------
    # Device Properties
    # -----------------

    GPIOPin = device_property(
        dtype='int16', default_value=4
    )

    # ----------
    # Attributes
    # ----------

    Temperature = attribute(
        dtype='double',
        label="Temperature",
        unit="C",
        standard_unit="C",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(TempSensorDS18B20.init_device) ENABLED START #
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.GPIOPin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        #GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.sensor=w1thermsensor.W1ThermSensor()
        self.set_state(PyTango.DevState.ON)
        self.running=True
        ctrlloop = ControlThread(self)
        ctrlloop.start()
        # PROTECTED REGION END #    //  TempSensorDS18B20.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(TempSensorDS18B20.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  TempSensorDS18B20.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(TempSensorDS18B20.delete_device) ENABLED START #
        self.running=False
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  TempSensorDS18B20.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Temperature(self):
        # PROTECTED REGION ID(TempSensorDS18B20.Temperature_read) ENABLED START #
        return float(self.temp)
        # PROTECTED REGION END #    //  TempSensorDS18B20.Temperature_read


    # --------
    # Commands
    # --------

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(TempSensorDS18B20.main) ENABLED START #
    return run((TempSensorDS18B20,), args=args, **kwargs)
    # PROTECTED REGION END #    //  TempSensorDS18B20.main

if __name__ == '__main__':
    main()
