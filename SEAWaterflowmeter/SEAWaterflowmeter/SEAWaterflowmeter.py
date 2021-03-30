# -*- coding: utf-8 -*-
#
# This file is part of the SEAWaterflowmeter project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" SeaWaterflowmeter

Device server to interface a Raspberry PI using the GPIO to the SEA YF-S201 water flow sensor.
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
# PROTECTED REGION ID(SEAWaterflowmeter.additionnal_import) ENABLED START #

from threading import Thread
import time
import RPi.GPIO as GPIO  
from time import sleep

count={} # Dictionary to keep counting the pulses from each flowmeter.

def my_callback(channel):
        global count
        count[channel]+=1

class ControlThread(Thread):
    
    def __init__ (self, ds):
        Thread.__init__(self)
        self.ds = ds
 
    def run(self):        
        global count
        while(self.ds.stop_ctrloop == 0):
            count=dict.fromkeys(count,0.0)
            time.sleep(self.ds.time)
            fixed=count.copy()
            self.ds.channel0data=float(list(fixed.values())[0])/(self.ds.time*self.ds.calibration)
            if (len(fixed)>1):
                self.ds.channel1data=float(list(fixed.values())[1])/(self.ds.time*self.ds.calibration)
            if (len(fixed)>2):
                self.ds.channel2data=float(list(fixed.values())[2])/(self.ds.time*self.ds.calibration)
            if (len(fixed)>3):
                self.ds.channel3data=float(list(fixed.values())[3])/(self.ds.time*self.ds.calibration)

 
        self.ds.set_state(PyTango.DevState.OFF)
        self.ds.stop_ctrloop = 0
        

# PROTECTED REGION END #    //  SEAWaterflowmeter.additionnal_import

__all__ = ["SEAWaterflowmeter", "main"]


class SEAWaterflowmeter(Device,metaclass=DeviceMeta):
    """
    Device server to interface a Raspberry PI using the GPIO to the SEA YF-S201 water flow sensor.
    """
    # PROTECTED REGION ID(SEAWaterflowmeter.class_variable) ENABLED START #
   
 
    # PROTECTED REGION END #    //  SEAWaterflowmeter.class_variable

    # -----------------
    # Device Properties
    # -----------------

    channels = device_property(
        dtype='str', default_value="6,13,19,26"
    )

    channelnames = device_property(
        dtype='str', default_value="turbo,xraygun,doser,p2lens"
    )

    calibration = device_property(
        dtype='double', default_value=7.5
    )

    time = device_property(
        dtype='double', default_value=1.0
    )

    # ----------
    # Attributes
    # ----------

    channel0 = attribute(
        dtype='double',
        label="turbo",
        unit="l/min",
        format="%3.1f",
    )

    channel1 = attribute(
        dtype='double',
        label="xray gun",
        unit="l/min",
        format="%3.1f",
    )

    channel2 = attribute(
        dtype='double',
        label="doser",
        unit="l/min",
        format="%3.1f",
    )

    channel3 = attribute(
        dtype='double',
        label="p2 lens",
        unit="l/min",
        format="%3.1f",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(SEAWaterflowmeter.init_device) ENABLED START #
        self.channel0data=0.0
        self.channel1data=0.0
        self.channel2data=0.0
        self.channel3data=0.0
        for i in self.channels.split(","):
            count[int(i)]=0.0
        self.listofnames=self.channelnames.split(",")
        #print(self.channel0.get_attribute_list)
        #self.channel0.set_label(listofnames[0])
        #self.channel1.set_label(listofnames[1])
        #self.channel2.set_label(listofnames[2])
        #self.channel3.set_label(listofnames[3])        
        GPIO.setmode(GPIO.BCM)     # set up BCM GPIO numbering  
        for i in count:
            GPIO.setup(i,GPIO.IN)
        for i in count:
            GPIO.add_event_detect(i, GPIO.RISING, callback=my_callback)  
        self.set_state(PyTango.DevState.ON)
        self.set_status("Measurement thread is running")
        self.stop_ctrloop = 0
        ctrlloop = ControlThread(self)
        ctrlloop.start()
        # PROTECTED REGION END #    //  SEAWaterflowmeter.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  SEAWaterflowmeter.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.delete_device) ENABLED START #
        self.ds.stop_ctrloop = 0
        GPIO.cleanup()
        # PROTECTED REGION END #    //  SEAWaterflowmeter.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_channel0(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.channel0_read) ENABLED START #
        return self.channel0data
        # PROTECTED REGION END #    //  SEAWaterflowmeter.channel0_read

    def read_channel1(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.channel1_read) ENABLED START #
        return self.channel1data
        # PROTECTED REGION END #    //  SEAWaterflowmeter.channel1_read

    def read_channel2(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.channel2_read) ENABLED START #
        return self.channel2data
        # PROTECTED REGION END #    //  SEAWaterflowmeter.channel2_read

    def read_channel3(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.channel3_read) ENABLED START #
        return self.channel3data
        # PROTECTED REGION END #    //  SEAWaterflowmeter.channel3_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def turnON(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.turnON) ENABLED START #
        state=self.get_state()
        if (state==PyTango.DevState.ON):
            return
        elif (state==PyTango.DevState.OFF):
            self.stop_ctrloop = 0
            ctrlloop = ControlThread(self)
            ctrlloop.start()
            self.set_state(PyTango.DevState.ON)
            self.set_status("Measurement thread is running")
        # PROTECTED REGION END #    //  SEAWaterflowmeter.turnON

    @command(
    )
    @DebugIt()
    def turnOFF(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.turnOFF) ENABLED START #
        state=self.get_state()
        if (state==PyTango.DevState.OFF):
            return
        elif (state==PyTango.DevState.ON):
            self.stop_ctrloop = 1
            self.set_state(PyTango.DevState.OFF)
            self.set_status("Measurement thread is NOT running")
        # PROTECTED REGION END #    //  SEAWaterflowmeter.turnOFF

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(SEAWaterflowmeter.main) ENABLED START #
    return run((SEAWaterflowmeter,), args=args, **kwargs)
    # PROTECTED REGION END #    //  SEAWaterflowmeter.main

if __name__ == '__main__':
    main()
