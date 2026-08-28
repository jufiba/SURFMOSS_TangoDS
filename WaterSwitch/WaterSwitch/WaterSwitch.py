# -*- coding: utf-8 -*-
#
# This file is part of the WaterSwitch project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" 

Simple device server to detect wheter water is flowing in a cooling water sensor
"""

# PyTango imports
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango import AttrQuality, DispLevel, DevState
from tango import AttrWriteType
# Additional import
# PROTECTED REGION ID(WaterSwitch.additionnal_import) ENABLED START #
import os
import sys
import atexit
import shutil
import tempfile
# rpi-lgpio pulls in lgpio, which on import drops a notification FIFO into the
# working directory. On these netbooted Pis that directory is the read-only NFS
# root, so the import dies with FileNotFoundError on '.lgd-nfy-3' -- where -3 is
# not a handle but the error code from failing to create the pipe. The name is
# per-process, not per-server, so two GPIO servers sharing a directory would
# also share the FIFO: give each process its own.
os.environ.setdefault("LG_WD", tempfile.mkdtemp(prefix="lgpio-"))
atexit.register(shutil.rmtree, os.environ["LG_WD"], True)
import RPi.GPIO as GPIO
# PROTECTED REGION END #    //  WaterSwitch.additionnal_import

__all__ = ["WaterSwitch", "main"]


class WaterSwitch(Device):
    """
    Simple device server to detect wheter water is flowing in a cooling water sensor
    """
    # PROTECTED REGION ID(WaterSwitch.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  WaterSwitch.class_variable

    # ----------
    # Attributes
    # ----------

    WaterFlowing = attribute(
        dtype='bool',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(WaterSwitch.init_device) ENABLED START #
        # An exception escaping init_device makes PyTango exit the whole
        # server, and taking a pin fails for reasons outside this device:
        # the kernel holding the line for an overlay gives lgpio.error:
        # 'GPIO busy', as w1-gpio did for GPIO 4 on pi-leem.
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(21, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        except Exception as e:                                # noqa: BLE001
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't take GPIO %s: %s" % (21, e))
            self.error_stream("Can't take GPIO %s: %s" % (21, e))
            return
        # The input is readable, which is all this server needs. It set
        # no state at all before, so it sat in UNKNOWN even when working,
        # and FAULT would have been its only meaningful state.
        self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  WaterSwitch.init_device
    def always_executed_hook(self):
        # PROTECTED REGION ID(WaterSwitch.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WaterSwitch.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(WaterSwitch.delete_device) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WaterSwitch.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_WaterFlowing(self):
        # PROTECTED REGION ID(WaterSwitch.WaterFlowing_read) ENABLED START #
        reading=GPIO.input(21)
        if (reading):
            self.set_state(tango.DevState.OFF)
            return False
        else:
            self.set_state(tango.DevState.ON)
            return True
        # PROTECTED REGION END #    //  WaterSwitch.WaterFlowing_read


    # --------
    # Commands
    # --------

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(WaterSwitch.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((WaterSwitch,), args=args, **kwargs)
    # PROTECTED REGION END #    //  WaterSwitch.main

if __name__ == '__main__':
    main()
