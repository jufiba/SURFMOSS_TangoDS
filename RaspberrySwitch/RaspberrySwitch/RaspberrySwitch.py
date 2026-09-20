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
from tango.server import Device
from tango.server import attribute, command
from tango.server import device_property
from tango import AttrQuality, DispLevel, DevState
from tango import AttrWriteType
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


class RaspberrySwitch(Device):
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
        self._ready = False
        self._switch = False
        # An exception escaping init_device makes PyTango exit the whole
        # server, and taking a pin fails for reasons outside this device:
        # the kernel holding the line for an overlay gives lgpio.error:
        # 'GPIO busy', as w1-gpio did for GPIO 4 on pi-leem.
        try:
            GPIO.setmode(GPIO.BCM)
            if (self.PullUPorDOWN==True):
                GPIO.setup(self.GPIOport, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            else:
                GPIO.setup(self.GPIOport, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        except Exception as e:                                # noqa: BLE001
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't take GPIO %s: %s" % (self.GPIOport, e))
            self.error_stream("Can't take GPIO %s: %s" % (self.GPIOport, e))
            return
        # The input is readable, which is all this server needs. It set
        # no state at all before, so it sat in UNKNOWN even when working,
        # and FAULT would have been its only meaningful state.
        self._ready = True
        self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  RaspberrySwitch.init_device
    def always_executed_hook(self):
        # PROTECTED REGION ID(RaspberrySwitch.always_executed_hook) ENABLED START #
        # Runs before every command or attribute, State included -- unlike a
        # State() read over CORBA, which never reaches read_Switch() at all.
        # AlarmNotifier watches bare State() and never reads an attribute, so
        # without this the state it sees was whatever the last client's
        # attribute read happened to leave behind, arbitrarily old, or just
        # the ON init_device set at start-up if nothing had read Switch yet.
        # GPIO.input() is a syscall, cheap enough to afford on every call.
        if not self._ready:
            return
        try:
            reading = GPIO.input(self.GPIOport)
        except Exception as e:                                # noqa: BLE001
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't read GPIO %s: %s" % (self.GPIOport, e))
            self.error_stream("Can't read GPIO %s: %s" % (self.GPIOport, e))
            return
        if (reading):
            if (self.Sense):
                self._switch = True
                self.set_state(tango.DevState.ON)
            else:
                self._switch = False
                self.set_state(tango.DevState.OFF)
        else:
            if (self.Sense):
                self._switch = False
                self.set_state(tango.DevState.OFF)
            else:
                self._switch = True
                self.set_state(tango.DevState.ON)
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
        # always_executed_hook has already read the pin and set State for
        # this same call; returning the value it computed avoids reading
        # GPIOport twice per attribute request.
        return self._switch
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
