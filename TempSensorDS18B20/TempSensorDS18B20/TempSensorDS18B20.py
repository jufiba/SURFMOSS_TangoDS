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
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import device_property
from tango import AttrQuality, DispLevel, DevState
from tango import AttrWriteType
# Additional import
# PROTECTED REGION ID(TempSensorDS18B20.additionnal_import) ENABLED START #
import os
import sys
import w1thermsensor

from threading import Thread, Event
import time

class ControlThread(Thread):

    def __init__ (self, ds):
        Thread.__init__(self, daemon=True)
        self.ds = ds

    def run(self):
        failures=0
        while not self.ds.stop.is_set():
            try:
                if self.ds.sensor is None:
                    self.ds.sensor=w1thermsensor.W1ThermSensor()
                self.ds.temp=self.ds.sensor.get_temperature()
                failures=0
                self.ds.set_state(tango.DevState.ON)
                self.ds.set_status("Reading DS18B20 %s"%self.ds.sensor.id)
            except Exception as e:
                # The 1-wire bus is noisy: the slave can drop out of
                # /sys/bus/w1/devices and reappear a few searches later. Retry
                # from scratch rather than dying and leaving Temperature frozen
                # on its last value.
                self.ds.sensor=None
                failures+=1
                if failures>=3:
                    self.ds.set_state(tango.DevState.FAULT)
                    self.ds.set_status("Can't read the DS18B20 sensor: %s"%e)
                    self.ds.error_stream("Can't read the DS18B20 sensor: %s"%e)
            self.ds.stop.wait(5)

# PROTECTED REGION END #    //  TempSensorDS18B20.additionnal_import

__all__ = ["TempSensorDS18B20", "main"]


class TempSensorDS18B20(Device):
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
        dtype='int16', default_value=4,
        doc='Which GPIO pin the sensor is wired to. Informational only: the '
            'pin is driven by the kernel w1-gpio overlay, configured in '
            'config.txt, not by this server.',
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
        # An Init on a running device must not leave the old loop behind,
        # writing self.temp underneath the new one.
        old=getattr(self,"ctrlloop",None)
        if old is not None:
            self.stop.set()
            old.join()
        self.stop=Event()
        self.sensor=None
        try:
            self.sensor=w1thermsensor.W1ThermSensor()
            self.set_state(tango.DevState.ON)
            self.set_status("Reading DS18B20 %s"%self.sensor.id)
        except Exception as e:
            # Letting this propagate makes PyTango exit the whole server, and
            # the Starter cannot then bring it back. Stay up in FAULT: the
            # control thread retries and recovers on its own if the sensor is
            # only temporarily missing.
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't find the DS18B20 sensor: %s"%e)
            self.error_stream("Can't find the DS18B20 sensor: %s"%e)
        self.ctrlloop = ControlThread(self)
        self.ctrlloop.start()
        # PROTECTED REGION END #    //  TempSensorDS18B20.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(TempSensorDS18B20.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  TempSensorDS18B20.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(TempSensorDS18B20.delete_device) ENABLED START #
        self.stop.set()
        self.set_state(tango.DevState.OFF)
        # PROTECTED REGION END #    //  TempSensorDS18B20.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Temperature(self):
        # PROTECTED REGION ID(TempSensorDS18B20.Temperature_read) ENABLED START #
        if self.sensor is None:
            # No sensor right now, so self.temp is stale: say so instead of
            # handing out an old number as if it were a fresh reading.
            return (float(self.temp), time.time(), tango.AttrQuality.ATTR_INVALID)
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
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((TempSensorDS18B20,), args=args, **kwargs)
    # PROTECTED REGION END #    //  TempSensorDS18B20.main

if __name__ == '__main__':
    main()
