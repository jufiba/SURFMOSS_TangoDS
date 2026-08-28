# -*- coding: utf-8 -*-
#
# This file is part of the ArduinoPt project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" ArduinoPt

An Arduino connected to a Pt module.
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
# PROTECTED REGION ID(ArduinoPt.additionnal_import) ENABLED START #
import os
import sys
import serial
# PROTECTED REGION END #    //  ArduinoPt.additionnal_import

__all__ = ["ArduinoPt", "main"]


class ArduinoPt(Device):
    """
    An Arduino connected to a Pt module.
    """
    # PROTECTED REGION ID(ArduinoPt.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  ArduinoPt.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str', default_value="/dev/ttyS0"
    )

    # ----------
    # Attributes
    # ----------

    Temperature = attribute(
        dtype='double',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(ArduinoPt.init_device) ENABLED START #
        # An exception escaping init_device makes PyTango exit the whole
        # server, and the Starter then leaves it for dead. FAULT with the
        # reason, not OFF: OFF means an instrument that answered and has
        # its output disabled.
        self.ser=None
        try:
            self.ser=serial.Serial(self.SerialPort,9600,bytesize=8,parity="N",stopbits=1,timeout=5)
        except (serial.SerialException,ValueError) as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't open %s: %s"%(self.SerialPort,e))
            self.error_stream("Can't open %s: %s"%(self.SerialPort,e))
            return
        try:
            self.ser.write(b"*PT\n")
            pt=self.ser.readline().decode("ascii").strip()
        except Exception as e:
            # Was OFF, which on these supplies means "output disabled".
            # Not being able to reach the Arduino is a different fact.
            self.set_state(tango.DevState.FAULT)
            self.set_status("No response from the Arduino on %s: %s"%(self.SerialPort,e))
            self.error_stream("No response from the Arduino on %s: %s"%(self.SerialPort,e))
            return
        if (not pt):
            # An empty line is what an absent board gives: readline() times out
            # and returns nothing, which raises nothing. Falling through to the
            # else below made silence read as "Pt resistor connected".
            self.set_state(tango.DevState.FAULT)
            self.set_status("No response from the Arduino on %s: it answered "
                            "*PT with an empty line"%self.SerialPort)
            self.error_stream("Empty answer to *PT on %s"%self.SerialPort)
        elif (pt=="Fault"):
            self.set_state(tango.DevState.FAULT)
            self.set_status("No Pt resistor connected")
            self.debug_stream("No Pt resistor connected to Arduino")
        else:
            self.set_state(tango.DevState.ON)
            self.set_status("Pt resistor connected")
            self.debug_stream("Pt resistor connected to Arduino")
        # PROTECTED REGION END #    //  ArduinoPt.init_device
    def always_executed_hook(self):
        # PROTECTED REGION ID(ArduinoPt.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  ArduinoPt.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(ArduinoPt.delete_device) ENABLED START #
        if (self.ser is not None):
            self.ser.close()
        # PROTECTED REGION END #    //  ArduinoPt.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Temperature(self):
        # PROTECTED REGION ID(ArduinoPt.Temperature_read) ENABLED START #
        try:
            self.ser.write(b"*PT\n")
            pt=self.ser.readline().decode("ascii").strip()
            if (pt=="Fault"):
                self.set_state(tango.DevState.FAULT)
                self.set_status("No Pt1000 resistor connected")
                self.debug_stream("No Pt1000 resistor connected to Arduino")
                return(0.0)
            else:
                return(float(pt))
        except:
            self.set_state(tango.DevState.OFF)
            self.set_status("No response from Arduino")
            self.debug_stream("No response from Arduino")
            return(0.0)
        # PROTECTED REGION END #    //  ArduinoPt.Temperature_read


    # --------
    # Commands
    # --------

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(ArduinoPt.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((ArduinoPt,), args=args, **kwargs)
    # PROTECTED REGION END #    //  ArduinoPt.main

if __name__ == '__main__':
    main()
