# -*- coding: utf-8 -*-
#
# This file is part of the AMLPGC1 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" AMLPGC1

Device server for AML PGC1.
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
# PROTECTED REGION ID(AMLPGC1.additionnal_import) ENABLED START #
import os
import sys
import time
import threading
import serial


class _Reconnect(threading.Thread):
    """Rebuild the serial link while it is down.

    After pi-leem is rebooted the PGC1 may not answer straight away (powered
    off, cable, or a PL2303 adapter that needs re-binding). Rather than
    leaving the server FAULT until an operator Init, retry every
    ReconnectPeriod seconds.
    """

    def __init__(self, ds):
        threading.Thread.__init__(self, name="AMLPGC1-reconnect", daemon=True)
        self.ds = ds
        self.stop = threading.Event()

    def run(self):
        while not self.stop.wait(self.ds.ReconnectPeriod):
            if self.ds.ser is None:
                self.ds.connect()


class _Deadman(threading.Thread):
    """Switch the ion gauge off if no Keepalive arrives within DeadmanTimeout.

    Same owner/decider split as RaspberryButton's DeadmanThread: the process
    that decides the ion gauge may run -- an AnalogInterlock watching a
    pressure or a cooling flow -- is not this one. If that process is killed
    its keepalives stop, and this thread then does what Stop does, so the
    failure of the supervisor drops the gauge HV by default.

    Disabled (DeadmanTimeout = 0) unless a device opts in, so every existing
    AMLPGC1 instance is unaffected.
    """

    def __init__(self, ds):
        threading.Thread.__init__(self, name="AMLPGC1-deadman", daemon=True)
        self.ds = ds
        self.stop = threading.Event()

    def run(self):
        ds = self.ds
        period = min(0.5, ds.DeadmanTimeout / 4.0)
        try:
            while not self.stop.wait(period):
                if not ds._gauge_asserted or ds._deadman_tripped:
                    continue
                idle = time.monotonic() - ds._last_keepalive
                if idle > ds.DeadmanTimeout:
                    try:
                        ds._cmd(b"*o0\r\n")          # switch off the ion gauge
                    except Exception as e:
                        ds.error_stream("Deadman could not stop the gauge: %s" % e)
                    ds._gauge_asserted = False
                    ds._deadman_tripped = True
                    msg = ("Deadman expired: no Keepalive for %.1f s (timeout "
                           "%.1f s). Ion gauge switched off; Start to restore."
                           % (idle, ds.DeadmanTimeout))
                    ds.set_state(tango.DevState.OFF)
                    ds.set_status(msg)
                    ds.error_stream(msg)
        except Exception as exc:
            # A dead deadman must not look healthy.
            ds.set_state(tango.DevState.FAULT)
            ds.set_status("Deadman thread died: %s" % exc)
            ds.error_stream("Deadman thread died: %s" % exc)
# PROTECTED REGION END #    //  AMLPGC1.additionnal_import

__all__ = ["AMLPGC1", "main"]


class AMLPGC1(Device):
    """
    Device server for AML PGC1.
    """
    # PROTECTED REGION ID(AMLPGC1.class_variable) ENABLED START #
    ser = None

    def connect(self):
        """Open the serial link and read one status reply. True if it is up.

        Never raises: a PGC1 that is not answering must leave the server
        FAULT, not take it down from init_device (see docs/DS-architecture.md).
        The short status reply is at least 8 bytes; byte 7 bit 0 is the
        ion-gauge on/off flag.
        """
        self.lastconnect = time.time()
        with self._io_lock:
            old, self.ser = self.ser, None
            if old is not None:
                try:
                    old.close()
                except Exception:
                    pass
            try:
                s = serial.Serial(self.SerialPort, baudrate=9600, bytesize=8,
                                  parity="N", stopbits=1, timeout=0.5)
                s.write(b"*S0\r\n")
                resp = s.readline()
            except Exception as e:
                self.set_state(tango.DevState.FAULT)
                self.set_status("Can't open %s: %s" % (self.SerialPort, e))
                self.error_stream("Can't open %s: %s" % (self.SerialPort, e))
                return False
            if len(resp) < 8:
                try:
                    s.close()
                except Exception:
                    pass
                self.set_state(tango.DevState.FAULT)
                self.set_status("No reply from AMLPGC1 on %s (%d bytes)"
                                % (self.SerialPort, len(resp)))
                self.error_stream("No reply from AMLPGC1 on %s (%d bytes)"
                                  % (self.SerialPort, len(resp)))
                return False
            self.ser = s
        self.set_status("Connected to AMLPGC1")
        self.debug_stream("Connected to AMLPGC1")
        self.set_state(tango.DevState.ON if resp[7] & 0b1
                       else tango.DevState.OFF)
        return True

    def _cmd(self, data, read=True):
        """One locked serial exchange. Raises a Tango error if the link is
        down. The reconnect and deadman threads run outside Tango's
        serialization monitor, so this is where their serial use is kept
        from interleaving with a client's."""
        with self._io_lock:
            if self.ser is None:
                tango.Except.throw_exception(
                    "AMLPGC1_NotConnected",
                    "no serial link to the AMLPGC1; it is powered off, "
                    "unplugged, or still coming up",
                    "AMLPGC1._cmd")
            self.ser.write(data)
            return self.ser.readline() if read else b""
    # PROTECTED REGION END #    //  AMLPGC1.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str',
    )

    ReconnectPeriod = device_property(
        dtype='double', default_value=10.0,
        doc='Seconds between attempts to rebuild the serial link while it '
            'is down.',
    )

    DeadmanTimeout = device_property(
        dtype='double', default_value=0.0,
        doc='Seconds without a Keepalive command after which the ion gauge '
            'is switched off, as Stop would. 0 disables the deadman '
            '(default). Set it comfortably above the restart time of '
            'whatever sends the keepalives -- an AnalogInterlock watching a '
            'pressure or cooling flow.',
    )

    # ----------
    # Attributes
    # ----------

    Pressure = attribute(
        dtype='double',
        unit="mbar",
        format="%.1e",
    )

    Remote = attribute(
        dtype='bool',
    )

    TimeSinceKeepalive = attribute(
        dtype='double',
        unit="s",
        format="%4.1f",
        doc="Seconds since the last Keepalive (or Start). Only meaningful "
            "with DeadmanTimeout set.",
    )

    DeadmanTripped = attribute(
        dtype='bool',
        doc="True after the deadman switched the ion gauge off for want of "
            "a Keepalive. Cleared by Start.",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(AMLPGC1.init_device) ENABLED START #
        self._io_lock = threading.Lock()
        self.ser = None
        self.lastconnect = 0
        self._reconnect = None
        self._deadman = None
        self._last_keepalive = time.monotonic()
        self._gauge_asserted = False
        self._deadman_tripped = False
        # connect() reports FAULT and returns rather than raising, so a PGC1
        # that is off no longer takes the server down.
        self.connect()
        self._reconnect = _Reconnect(self)
        self._reconnect.start()
        if self.DeadmanTimeout > 0.0:
            self._deadman = _Deadman(self)
            self._deadman.start()
        # PROTECTED REGION END #    //  AMLPGC1.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(AMLPGC1.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  AMLPGC1.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(AMLPGC1.delete_device) ENABLED START #
        if getattr(self, "_reconnect", None) is not None:
            self._reconnect.stop.set()
        if getattr(self, "_deadman", None) is not None:
            self._deadman.stop.set()
        # Deliberately does NOT switch the gauge off: an Init from Jive must
        # not disturb a running experiment. If this server is gone for good
        # the deadman cannot help either -- it is the interlock dying that it
        # guards against, not this server.
        if self.ser is None:
            return
        try:
            a = self._cmd(b"*P0\r\n")
            if len(a) > 0 and a[0] & 0b10000 == 0b10000:
                self._cmd(b"*R0\r\n")
        except Exception as e:
            self.debug_stream("Untidy disconnect: %s" % e)
        try:
            with self._io_lock:
                if self.ser is not None:
                    self.ser.close()
        except Exception:
            pass
        # PROTECTED REGION END #    //  AMLPGC1.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Pressure(self):
        # PROTECTED REGION ID(AMLPGC1.Pressure_read) ENABLED START #
        a = self._cmd(b"*S0\r\n")
        pressure = a[9:].split(b",")[0]
        return float(pressure)
        # PROTECTED REGION END #    //  AMLPGC1.Pressure_read

    def read_Remote(self):
        # PROTECTED REGION ID(AMLPGC1.Remote_read) ENABLED START #
        a = self._cmd(b"*P0\r\n")
        return len(a) > 0 and a[0] & 0b10000 == 0b10000
        # PROTECTED REGION END #    //  AMLPGC1.Remote_read

    def read_TimeSinceKeepalive(self):
        # PROTECTED REGION ID(AMLPGC1.TimeSinceKeepalive_read) ENABLED START #
        return time.monotonic() - self._last_keepalive
        # PROTECTED REGION END #    //  AMLPGC1.TimeSinceKeepalive_read

    def read_DeadmanTripped(self):
        # PROTECTED REGION ID(AMLPGC1.DeadmanTripped_read) ENABLED START #
        return self._deadman_tripped
        # PROTECTED REGION END #    //  AMLPGC1.DeadmanTripped_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def Start(self):
        # PROTECTED REGION ID(AMLPGC1.Start) ENABLED START #
        # Turn on the ion gauge with auto emission control (*i03). Also
        # arms/refreshes the deadman and clears a trip: a Start by hand from
        # Jive then persists only while something keeps sending Keepalive.
        self._cmd(b"*i03\r\n")
        self._last_keepalive = time.monotonic()
        self._gauge_asserted = True
        self._deadman_tripped = False
        self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  AMLPGC1.Start

    @command(
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(AMLPGC1.Stop) ENABLED START #
        self._cmd(b"*o0\r\n")
        self._gauge_asserted = False
        self.set_state(tango.DevState.OFF)
        # PROTECTED REGION END #    //  AMLPGC1.Stop

    @command(
    )
    @DebugIt()
    def Keepalive(self):
        # PROTECTED REGION ID(AMLPGC1.Keepalive) ENABLED START #
        # Refreshes the deadman timer only. Never touches the gauge:
        # recovering from a deadman trip needs an explicit Start.
        self._last_keepalive = time.monotonic()
        # PROTECTED REGION END #    //  AMLPGC1.Keepalive

    @command(
    dtype_in='str',
    dtype_out='str',
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def setCommand(self, argin):
        # PROTECTED REGION ID(AMLPGC1.setCommand) ENABLED START #
        return self._cmd(("*"+argin+"\r\n").encode("ascii")).decode("ascii", "replace")
        # PROTECTED REGION END #    //  AMLPGC1.setCommand

    @command(
    )
    @DebugIt()
    def SetLocal(self):
        # PROTECTED REGION ID(AMLPGC1.SetLocal) ENABLED START #
        self._cmd(b"*R0\r\n")
        self._gauge_asserted = False
        self.set_state(tango.DevState.OFF)
        # PROTECTED REGION END #    //  AMLPGC1.SetLocal

    @command(
    )
    @DebugIt()
    def SetRemote(self):
        # PROTECTED REGION ID(AMLPGC1.SetRemote) ENABLED START #
        self._cmd(b"*C0\r\n") # Set remote mode
        self.set_state(tango.DevState.OFF)
        # PROTECTED REGION END #    //  AMLPGC1.SetRemote

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(AMLPGC1.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((AMLPGC1,), args=args, **kwargs)
    # PROTECTED REGION END #    //  AMLPGC1.main

if __name__ == '__main__':
    main()
