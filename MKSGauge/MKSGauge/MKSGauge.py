# -*- coding: utf-8 -*-
#
# This file is part of the MKSGauge project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" MKSGauge Reader

This is a very simple reader for the PDR9000 unit with a 972B transducer.
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
# PROTECTED REGION ID(MKSGauge.additionnal_import) ENABLED START #
import os
import sys
import time
import serial
# PROTECTED REGION END #    //  MKSGauge.additionnal_import

__all__ = ["MKSGauge", "main"]


class MKSGauge(Device):
    """
    This is a very simple reader for the PDR9000 unit with a 972B transducer.
    """
    # PROTECTED REGION ID(MKSGauge.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  MKSGauge.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str',
        mandatory=True
    )

    Speed = device_property(
        dtype='uint',
        mandatory=True
    )

    # ----------
    # Attributes
    # ----------

    Pressure = attribute(
        dtype='double',
        label="Pressure",
        unit="mbar",
        standard_unit="mbar",
        display_unit="mbar",
        format="%4.2e",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(MKSGauge.init_device) ENABLED START #
        # An exception escaping init_device makes PyTango exit the whole
        # server, and the Starter then leaves it for dead. FAULT with the
        # reason, not OFF: OFF means an instrument that answered and has
        # its output disabled.
        self.ser=None
        try:
            self.ser=serial.Serial(self.SerialPort,baudrate=self.Speed,bytesize=8,parity="N",stopbits=1,timeout=0.5)
        except (serial.SerialException,ValueError) as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't open %s: %s"%(self.SerialPort,e))
            self.error_stream("Can't open %s: %s"%(self.SerialPort,e))
            return
        self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  MKSGauge.init_device
    def always_executed_hook(self):
        # PROTECTED REGION ID(MKSGauge.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  MKSGauge.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(MKSGauge.delete_device) ENABLED START #
        if (self.ser is not None):
            self.ser.close()
        # PROTECTED REGION END #    //  MKSGauge.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Pressure(self):
        # PROTECTED REGION ID(MKSGauge.Pressure_read) ENABLED START #
        if self.ser is None:
            return (0.0, time.time(), tango.AttrQuality.ATTR_INVALID)
        self.ser.write(b"@254PR4?;FF")
        a=self.ser.read_until(b";FF")
        if (a[0:7]==b"@253ACK"):
            try:
                return float(a[7:15])
            except ValueError:
                pass
        # 0.0 on a pressure gauge reads as perfect vacuum -- the worst value
        # to hand an interlock or an alarm. A non-ACK, empty or unparseable
        # reply is INVALID, not 9999 mbar (a number a client could act on).
        return (0.0, time.time(), tango.AttrQuality.ATTR_INVALID)
        # PROTECTED REGION END #    //  MKSGauge.Pressure_read


    # --------
    # Commands
    # --------

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def sendCommand(self, argin):
        # PROTECTED REGION ID(MKSGauge.sendCommand) ENABLED START #
        self.ser.write((argin+";FF").encode("ascii"))
        return self.ser.read_until(b";FF").decode("ascii")
        # PROTECTED REGION END #    //  MKSGauge.sendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(MKSGauge.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((MKSGauge,), args=args, **kwargs)
    # PROTECTED REGION END #    //  MKSGauge.main

if __name__ == '__main__':
    main()
