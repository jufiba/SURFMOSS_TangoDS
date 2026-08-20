# -*- coding: utf-8 -*-
#
# This file is part of the Keithley2100 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" Keithley2100

Server for Keithley DVMM 61/2 digits
"""

# PyTango imports
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device, DeviceMeta
from tango.server import attribute, command
from tango.server import device_property
from tango import AttrQuality, DispLevel, DevState
from tango import AttrWriteType, PipeWriteType
# Additional import
# PROTECTED REGION ID(Keithley2100.additionnal_import) ENABLED START #
import os
import sys
import usbtmc
# PROTECTED REGION END #    //  Keithley2100.additionnal_import

__all__ = ["Keithley2100", "main"]


class Keithley2100(Device, metaclass=DeviceMeta):
    """
    Server for Keithley DVMM 61/2 digits
    """
    # PROTECTED REGION ID(Keithley2100.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  Keithley2100.class_variable

    # -----------------
    # Device Properties
    # -----------------

    idProduct = device_property(
        dtype='uint', default_value=8448
    )

    idVendor = device_property(
        dtype='uint', default_value=1510
    )

    # ----------
    # Attributes
    # ----------

    Field = attribute(
        dtype='double',
        unit="T",
        format="%5.4f",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(Keithley2100.init_device) ENABLED START #
        #instr=usbtmc.Instrument(idVendor,idProduct)
        self.instr=usbtmc.Instrument(0x05e6,0x2100)
        self.set_status("Connected to DVMM Keithley 2100")
        self.debug_stream("Connected to DVMM Keithley 2100")
        self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  Keithley2100.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(Keithley2100.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  Keithley2100.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(Keithley2100.delete_device) ENABLED START #
        pass
        # PROTECTED REGION END #    //  Keithley2100.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Field(self):
        # PROTECTED REGION ID(Keithley2100.Field_read) ENABLED START #
        return float(self.instr.ask("MEAS:VOLT:DC?"))*10.0
        # PROTECTED REGION END #    //  Keithley2100.Field_read


    # --------
    # Commands
    # --------

    @command(
    dtype_in='str', 
    dtype_out='str', 
    )
    @DebugIt()
    def sendCommand(self, argin):
        # PROTECTED REGION ID(Keithley2100.sendCommand) ENABLED START #
        return self.instr.ask(argin)
        # PROTECTED REGION END #    //  Keithley2100.sendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(Keithley2100.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((Keithley2100,), args=args, **kwargs)
    # PROTECTED REGION END #    //  Keithley2100.main

if __name__ == '__main__':
    main()
