# -*- coding: utf-8 -*-
#
# This file is part of the RaspberrySwitch project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" RaspberrySwitch

Read a switch connected to one of the GPIO pins.
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
# PROTECTED REGION ID(RaspberrySwitch.additionnal_import) ENABLED START #
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
# PROTECTED REGION END #    //  RaspberrySwitch.additionnal_import

__all__ = ["RaspberrySwitch", "main"]


class RaspberrySwitch(Device, metaclass=DeviceMeta):
    """
    Read a switch connected to one of the GPIO pins.
    """
    # PROTECTED REGION ID(RaspberrySwitch.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  RaspberrySwitch.class_variable

    # -----------------
    # Device Properties
    # -----------------

    GPIOport = device_property(
        dtype='uint16',
    )

    PullUPorDOWN = device_property(
        dtype='bool',
    )

    Sense = device_property(
        dtype='bool', default_value=True
    )

    # ----------
    # Attributes
    # ----------

    Switch = attribute(
        dtype='bool',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(RaspberrySwitch.init_device) ENABLED START #
        GPIO.setmode(GPIO.BCM)
        if (self.PullUPorDOWN==True):
            GPIO.setup(self.GPIOport, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        else:
           GPIO.setup(self.GPIOport, GPIO.IN, pull_up_down=GPIO.PUD_DOWN) 
        # PROTECTED REGION END #    //  RaspberrySwitch.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(RaspberrySwitch.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  RaspberrySwitch.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(RaspberrySwitch.delete_device) ENABLED START #
        pass
        # PROTECTED REGION END #    //  RaspberrySwitch.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Switch(self):
        # PROTECTED REGION ID(RaspberrySwitch.Switch_read) ENABLED START #
        reading=GPIO.input(self.GPIOport)
        if (reading):
            if (self.Sense):
                self.set_state(tango.DevState.ON)
                return True
            else:
                self.set_state(tango.DevState.OFF)
                return False
        else:
            if (self.Sense):
                self.set_state(tango.DevState.OFF)
                return False
            else:
                self.set_state(tango.DevState.ON)
                return True
        # PROTECTED REGION END #    //  RaspberrySwitch.Switch_read


    # --------
    # Commands
    # --------

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(RaspberrySwitch.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((RaspberrySwitch,), args=args, **kwargs)
    # PROTECTED REGION END #    //  RaspberrySwitch.main

if __name__ == '__main__':
    main()
