# -*- coding: utf-8 -*-
#
# This file is part of the WisselMCA project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" WisselMCA

Device server for the Wissel Multichannel Analyzer used for M�ssbauer spectroscopy.
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
# PROTECTED REGION ID(WisselMCA.additionnal_import) ENABLED START #
# PROTECTED REGION END #    //  WisselMCA.additionnal_import

__all__ = ["WisselMCA", "main"]


class WisselMCA(Device, metaclass=DeviceMeta):
    """
    Device server for the Wissel Multichannel Analyzer used for M\xf6ssbauer spectroscopy.
    """
    # PROTECTED REGION ID(WisselMCA.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  WisselMCA.class_variable

    # -----------------
    # Device Properties
    # -----------------

    vendorid = device_property(
        dtype='uint16', default_value=0x0925
    )

    instrumentID = device_property(
        dtype='uint16', default_value=0x0035
    )

    # ----------
    # Attributes
    # ----------

    Lower_Window_Limit = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        label="Lower Limit",
        unit="mV",
        standard_unit="mV",
        format="%5.0f",
        max_value=10000,
    )

    Upper_Window_Limit = attribute(
        dtype='double',
        label="Upper Limit",
        unit="mV",
        standard_unit="mV",
        format="%5.0f",
        max_value=10000,
        min_value=0,
    )

    Model = attribute(
        dtype='str',
        display_level=DispLevel.EXPERT,
    )

    Configuration = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
    )

    Folded = attribute(
        dtype='bool',
        access=AttrWriteType.WRITE,
    )

    Fold_Channel = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
    )

    Mode = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
    )

    Spectrum = attribute(
        dtype=('uint64',),
        max_dim_x=8192,
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(WisselMCA.init_device) ENABLED START #
        # PROTECTED REGION END #    //  WisselMCA.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(WisselMCA.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WisselMCA.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(WisselMCA.delete_device) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WisselMCA.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Lower_Window_Limit(self):
        # PROTECTED REGION ID(WisselMCA.Lower_Window_Limit_read) ENABLED START #
        return 0.0
        # PROTECTED REGION END #    //  WisselMCA.Lower_Window_Limit_read

    def write_Lower_Window_Limit(self, value):
        # PROTECTED REGION ID(WisselMCA.Lower_Window_Limit_write) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WisselMCA.Lower_Window_Limit_write

    def read_Upper_Window_Limit(self):
        # PROTECTED REGION ID(WisselMCA.Upper_Window_Limit_read) ENABLED START #
        return 0.0
        # PROTECTED REGION END #    //  WisselMCA.Upper_Window_Limit_read

    def read_Model(self):
        # PROTECTED REGION ID(WisselMCA.Model_read) ENABLED START #
        return ''
        # PROTECTED REGION END #    //  WisselMCA.Model_read

    def read_Configuration(self):
        # PROTECTED REGION ID(WisselMCA.Configuration_read) ENABLED START #
        return 0
        # PROTECTED REGION END #    //  WisselMCA.Configuration_read

    def write_Configuration(self, value):
        # PROTECTED REGION ID(WisselMCA.Configuration_write) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WisselMCA.Configuration_write

    def write_Folded(self, value):
        # PROTECTED REGION ID(WisselMCA.Folded_write) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WisselMCA.Folded_write

    def read_Fold_Channel(self):
        # PROTECTED REGION ID(WisselMCA.Fold_Channel_read) ENABLED START #
        return 0
        # PROTECTED REGION END #    //  WisselMCA.Fold_Channel_read

    def write_Fold_Channel(self, value):
        # PROTECTED REGION ID(WisselMCA.Fold_Channel_write) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WisselMCA.Fold_Channel_write

    def read_Mode(self):
        # PROTECTED REGION ID(WisselMCA.Mode_read) ENABLED START #
        return 0.0
        # PROTECTED REGION END #    //  WisselMCA.Mode_read

    def write_Mode(self, value):
        # PROTECTED REGION ID(WisselMCA.Mode_write) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WisselMCA.Mode_write

    def read_Spectrum(self):
        # PROTECTED REGION ID(WisselMCA.Spectrum_read) ENABLED START #
        return [0]
        # PROTECTED REGION END #    //  WisselMCA.Spectrum_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def Start(self):
        # PROTECTED REGION ID(WisselMCA.Start) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WisselMCA.Start

    @command(
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(WisselMCA.Stop) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WisselMCA.Stop

    @command(
    )
    @DebugIt()
    def setPHAmode(self):
        # PROTECTED REGION ID(WisselMCA.setPHAmode) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WisselMCA.setPHAmode

    @command(
    )
    @DebugIt()
    def setMCAmode(self):
        # PROTECTED REGION ID(WisselMCA.setMCAmode) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WisselMCA.setMCAmode

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(WisselMCA.main) ENABLED START #
    return run((WisselMCA,), args=args, **kwargs)
    # PROTECTED REGION END #    //  WisselMCA.main

if __name__ == '__main__':
    main()
