# -*- coding: utf-8 -*-
#
# This file is part of the NetworkUPSTool project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" NetworkUPSTool

A wrapper for showing the more relevant information from NUT, the network UPS tool.
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
# PROTECTED REGION ID(NetworkUPSTool.additionnal_import) ENABLED START #
import PyNUT
# PROTECTED REGION END #    //  NetworkUPSTool.additionnal_import

__all__ = ["NetworkUPSTool", "main"]


class NetworkUPSTool(Device):
    """
    A wrapper for showing the more relevant information from NUT, the network UPS tool.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(NetworkUPSTool.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  NetworkUPSTool.class_variable

    # -----------------
    # Device Properties
    # -----------------

    UPSunitName = device_property(
        dtype='str',
    )

    # ----------
    # Attributes
    # ----------

    UpsStatus = attribute(
        dtype='str',
    )

    Temperature = attribute(
        dtype='double',
        label="Temperature",
        unit="ºC",
    )

    Load = attribute(
        dtype='double',
        label="Load",
        unit="%",
    )

    Charge = attribute(
        dtype='double',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(NetworkUPSTool.init_device) ENABLED START #
        self.client=PyNUT.PyNUTClient()
        self.varsUPS=self.client.GetUPSVars(self.UPSunitName)
        self.commUPS=self.client.GetUPSCommands(self.UPSunitName)
        if (self.varsUPS["ups.status"]=="OL"):
            self.set_state(PyTango.DevState.ON)
        elif (self.varsUPS["ups.status"]=="OB"):
            self.set_state(PyTango.DevState.STANDBY)
        else:
            self.set_state(PyTango.DevState.FAULT)
        # PROTECTED REGION END #    //  NetworkUPSTool.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(NetworkUPSTool.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  NetworkUPSTool.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(NetworkUPSTool.delete_device) ENABLED START #
        pass
        # PROTECTED REGION END #    //  NetworkUPSTool.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_UpsStatus(self):
        # PROTECTED REGION ID(NetworkUPSTool.UpsStatus_read) ENABLED START #
        self.varsUPS=self.client.GetUPSVars(self.UPSunitName)
        if (self.varsUPS["ups.status"]=="OL"):
            self.set_state(PyTango.DevState.ON)
            status="OnLine"
        elif (self.varsUPS["ups.status"]=="OB"):
            self.set_state(PyTango.DevState.STANDBY)
            status="OnBattery"
        else:
            self.set_state(PyTango.DevState.FAULT)
            status=self.varsUPS["ups.status"]
        return status
        # PROTECTED REGION END #    //  NetworkUPSTool.UpsStatus_read

    def read_Temperature(self):
        # PROTECTED REGION ID(NetworkUPSTool.Temperature_read) ENABLED START #
        self.varsUPS=self.client.GetUPSVars(self.UPSunitName)
        return (float(self.varsUPS["ups.temperature"]))
        # PROTECTED REGION END #    //  NetworkUPSTool.Temperature_read

    def read_Load(self):
        # PROTECTED REGION ID(NetworkUPSTool.Load_read) ENABLED START #
        self.varsUPS=self.client.GetUPSVars(self.UPSunitName)
        return (float(self.varsUPS["ups.load"]))
        # PROTECTED REGION END #    //  NetworkUPSTool.Load_read

    def read_Charge(self):
        # PROTECTED REGION ID(NetworkUPSTool.Charge_read) ENABLED START #
        self.varsUPS=self.client.GetUPSVars(self.UPSunitName)
        return (float(self.varsUPS["battery.charge"]))
        # PROTECTED REGION END #    //  NetworkUPSTool.Charge_read


    # --------
    # Commands
    # --------

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(NetworkUPSTool.main) ENABLED START #
    return run((NetworkUPSTool,), args=args, **kwargs)
    # PROTECTED REGION END #    //  NetworkUPSTool.main

if __name__ == '__main__':
    main()
