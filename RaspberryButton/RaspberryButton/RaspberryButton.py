# -*- coding: utf-8 -*-
#
# This file is part of the RaspberryButton project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" RaspberryButton

Simple interface to turn on and off a GPIO pin in a Raspberry PI.
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
# PROTECTED REGION ID(RaspberryButton.additionnal_import) ENABLED START #
import os
import sys
import time
import atexit
import shutil
import tempfile
import threading

# rpi-lgpio pulls in lgpio, which on import drops a notification FIFO into the
# working directory. On the netbooted Pis that directory is the read-only NFS
# root, so the import dies with FileNotFoundError on '.lgd-nfy-3' -- where -3 is
# not a handle but the error code from failing to create the pipe. The name is
# per-process, not per-server, so two GPIO servers sharing a directory would
# also share the FIFO: give each process its own. Harmless where the original
# RPi.GPIO is installed, which never reads LG_WD.
os.environ.setdefault("LG_WD", tempfile.mkdtemp(prefix="lgpio-"))
atexit.register(shutil.rmtree, os.environ["LG_WD"], True)
import RPi.GPIO as GPIO


class DeadmanThread(threading.Thread):
    """Drops the pin if no Keepalive arrives within DeadmanTimeout seconds.

    This exists because the process that *decides* whether the output should be
    asserted (an interlock device server) and the process that *owns* the output
    are different processes. If the deciding process is killed, nothing else
    would ever release the pin: RPi.GPIO leaves an output pin latched at its
    last level when the owning process dies, and a killed process does not run
    delete_device. Putting the timeout in the process that owns the pin means
    the failure of any external supervisor de-asserts the output by default.

    Disabled (DeadmanTimeout = 0) unless a device explicitly opts in, so the
    behaviour of every other RaspberryButton instance is unchanged.
    """

    def __init__(self, ds):
        threading.Thread.__init__(self, name="RaspberryButton-deadman")
        self.daemon = True
        self.ds = ds

    def run(self):
        ds = self.ds
        period = min(0.5, ds.DeadmanTimeout / 4.0)
        try:
            while not ds.stop_event.wait(period):
                if ds.get_state() != PyTango.DevState.ON:
                    continue
                idle = time.monotonic() - ds.last_keepalive
                if idle > ds.DeadmanTimeout:
                    ds.drive(False)
                    ds.deadman_tripped = True
                    ds.set_state(PyTango.DevState.ALARM)
                    ds.set_status(
                        "Deadman expired: no Keepalive for %.1f s "
                        "(timeout %.1f s). Output de-asserted."
                        % (idle, ds.DeadmanTimeout))
        except Exception as exc:
            # A dead deadman must not look healthy.
            ds.drive(False)
            ds.set_state(PyTango.DevState.FAULT)
            ds.set_status("Deadman thread died: %s" % exc)


# PROTECTED REGION END #    //  RaspberryButton.additionnal_import

__all__ = ["RaspberryButton", "main"]


class RaspberryButton(Device, metaclass=DeviceMeta):
    """
    Simple interface to turn on and off a GPIO pin in a Raspberry PI.
    """
    # PROTECTED REGION ID(RaspberryButton.class_variable) ENABLED START #
    # drive() lives here because class_variable is the only region inside the
    # class body that this POGO template emits, and so the only one it keeps
    # when the code is regenerated from the .xmi.
    def drive(self, active):
        """Set the electrical level corresponding to a logical state."""
        if self.TrueHigh:
            GPIO.output(self.Pin, GPIO.HIGH if active else GPIO.LOW)
        else:
            GPIO.output(self.Pin, GPIO.LOW if active else GPIO.HIGH)
    # PROTECTED REGION END #    //  RaspberryButton.class_variable

    # -----------------
    # Device Properties
    # -----------------

    Pin = device_property(
        dtype='uint16',
    )

    TrueHigh = device_property(
        dtype='bool',
    )

    DeadmanTimeout = device_property(
        dtype='double', default_value=0.0,
        doc="Seconds without a Keepalive command after which the output is "
            "de-asserted. 0 disables the deadman entirely (default). Must be "
            "comfortably longer than a restart of whatever sends the "
            "keepalives, or restarting that server will drop the output.",
    )

    # ----------
    # Attributes
    # ----------

    PinLevel = attribute(
        dtype='bool',
        label="PinLevel",
        doc="Electrical level read back from the pin, before TrueHigh is "
            "applied. Disagreement with Active means something else has "
            "reconfigured the pin.",
    )

    Active = attribute(
        dtype='bool',
        label="Active",
        doc="Logical output state: True when the pin is asserted, taking "
            "TrueHigh into account.",
    )

    TimeSinceKeepalive = attribute(
        dtype='double',
        label="TimeSinceKeepalive",
        unit="s",
        format="%4.1f",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(RaspberryButton.init_device) ENABLED START #
        self.stop_event = threading.Event()
        self.stop_event.set()
        self.deadman = None
        self.deadman_tripped = False
        self.last_keepalive = time.monotonic()

        # The pin is deliberately left claimed as an output across device
        # restarts (see delete_device), so RPi.GPIO would warn about it being
        # already in use. That is the intended state, not a mistake.
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        # initial= makes claiming the pin and setting its inactive level a
        # single operation. Without it there is a window between setup() and
        # output() in which the level is whatever the previous configuration
        # left behind.
        inactive = GPIO.LOW if self.TrueHigh else GPIO.HIGH
        GPIO.setup(self.Pin, GPIO.OUT, initial=inactive)

        self.set_state(PyTango.DevState.OFF)
        self.set_status("Output de-asserted")

        if self.DeadmanTimeout > 0.0:
            self.stop_event.clear()
            self.deadman = DeadmanThread(self)
            self.deadman.start()
            self.set_status("Output de-asserted; deadman armed (%.1f s)"
                            % self.DeadmanTimeout)
        # PROTECTED REGION END #    //  RaspberryButton.init_device


    def always_executed_hook(self):
        # PROTECTED REGION ID(RaspberryButton.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  RaspberryButton.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(RaspberryButton.delete_device) ENABLED START #
        self.stop_event.set()
        if self.deadman is not None and self.deadman.is_alive():
            self.deadman.join(timeout=2.0)

        # Leave the pin as a driven output at its inactive level rather than
        # calling GPIO.cleanup(). cleanup() returns the pin to an input with no
        # pull, i.e. floating, and what the relay box then sees depends on
        # whatever pull it happens to provide. A driven inactive output is
        # unambiguous. A bare cleanup() would also release every pin claimed by
        # sibling devices in the same server process.
        try:
            self.drive(False)
        except Exception:
            pass
        # PROTECTED REGION END #    //  RaspberryButton.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_PinLevel(self):
        # PROTECTED REGION ID(RaspberryButton.PinLevel_read) ENABLED START #
        return bool(GPIO.input(self.Pin))
        # PROTECTED REGION END #    //  RaspberryButton.PinLevel_read

    def read_Active(self):
        # PROTECTED REGION ID(RaspberryButton.Active_read) ENABLED START #
        level = bool(GPIO.input(self.Pin))
        return level if self.TrueHigh else not level
        # PROTECTED REGION END #    //  RaspberryButton.Active_read

    def read_TimeSinceKeepalive(self):
        # PROTECTED REGION ID(RaspberryButton.TimeSinceKeepalive_read) ENABLED START #
        return time.monotonic() - self.last_keepalive
        # PROTECTED REGION END #    //  RaspberryButton.TimeSinceKeepalive_read

    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def On(self):
        # PROTECTED REGION ID(RaspberryButton.On) ENABLED START #
        # Asserting the output also arms the deadman. With DeadmanTimeout set,
        # an On() issued by hand from Jive therefore persists only as long as
        # something keeps sending Keepalive, which is the point.
        self.last_keepalive = time.monotonic()
        self.deadman_tripped = False
        self.drive(True)
        self.set_state(PyTango.DevState.ON)
        self.set_status("Output asserted")
        # PROTECTED REGION END #    //  RaspberryButton.On

    @command(
    )
    @DebugIt()
    def Off(self):
        # PROTECTED REGION ID(RaspberryButton.Off) ENABLED START #
        self.drive(False)
        self.set_state(PyTango.DevState.OFF)
        self.set_status("Output de-asserted")
        # PROTECTED REGION END #    //  RaspberryButton.Off

    @command(
    )
    @DebugIt()
    def Keepalive(self):
        # PROTECTED REGION ID(RaspberryButton.Keepalive) ENABLED START #
        # Refreshes the deadman only. It never asserts the output: recovering
        # from a trip requires an explicit On().
        self.last_keepalive = time.monotonic()
        # PROTECTED REGION END #    //  RaspberryButton.Keepalive

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(RaspberryButton.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((RaspberryButton,), args=args, **kwargs)
    # PROTECTED REGION END #    //  RaspberryButton.main


if __name__ == '__main__':
    main()
