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
# PROTECTED REGION END #    //  SEAWaterflowmeter.additionnal_import

__all__ = ["SEAWaterflowmeter", "main"]


class SEAWaterflowmeter(Device):
    """
    Device server to interface a Raspberry PI using the GPIO to the SEA YF-S201 water flow sensor.
    """
    __metaclass__ = DeviceMeta
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

    # ----------
    # Attributes
    # ----------

    channel0 = attribute(
        dtype='double',
        unit="l/min",
        format="%3.1f",
    )

    channel1 = attribute(
        dtype='double',
        unit="l/min",
        format="%3.1f",
    )

    channel2 = attribute(
        dtype='double',
        unit="l/min",
        format="%3.1f",
    )

    channel3 = attribute(
        dtype='double',
        unit="l/min",
        format="%3.1f",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(SEAWaterflowmeter.init_device) ENABLED START #
        # PROTECTED REGION END #    //  SEAWaterflowmeter.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  SEAWaterflowmeter.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.delete_device) ENABLED START #
        pass
        # PROTECTED REGION END #    //  SEAWaterflowmeter.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_channel0(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.channel0_read) ENABLED START #
        return 0.0
        # PROTECTED REGION END #    //  SEAWaterflowmeter.channel0_read

    def read_channel1(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.channel1_read) ENABLED START #
        return 0.0
        # PROTECTED REGION END #    //  SEAWaterflowmeter.channel1_read

    def read_channel2(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.channel2_read) ENABLED START #
        return 0.0
        # PROTECTED REGION END #    //  SEAWaterflowmeter.channel2_read

    def read_channel3(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.channel3_read) ENABLED START #
        return 0.0
        # PROTECTED REGION END #    //  SEAWaterflowmeter.channel3_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def turnON(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.turnON) ENABLED START #
        pass
        # PROTECTED REGION END #    //  SEAWaterflowmeter.turnON

    @command(
    )
    @DebugIt()
    def turnOFF(self):
        # PROTECTED REGION ID(SEAWaterflowmeter.turnOFF) ENABLED START #
        pass
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
