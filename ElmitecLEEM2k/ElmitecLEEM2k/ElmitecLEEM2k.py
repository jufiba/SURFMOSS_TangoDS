# -*- coding: utf-8 -*-
#
# This file is part of the ElmitecLEEM2k project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" ElmitecLEEM2k

Device server for accessing the settings of the LEEM2000 program from Elmitec.
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
# PROTECTED REGION ID(ElmitecLEEM2k.additionnal_import) ENABLED START #
import os
import sys
import time
import socket
import threading


class ElmitecLEEM2kError(Exception):
    """LEEM2000 is not there, or stopped answering part way through an exchange."""


class _Reconnect(threading.Thread):
    """Rebuild the link while it is down, so a restart of LEEM2000 does
    not need this server restarted too.

    LEEM2000 is restarted often, and until now each restart meant
    restarting this device server by hand.
    """

    def __init__(self, ds):
        threading.Thread.__init__(self, daemon=True)
        self.ds = ds
        self.stop = threading.Event()

    def run(self):
        while not self.stop.wait(self.ds.ReconnectPeriod):
            if not self.ds.ElmitecLEEM2kConnected:
                self.ds.connect()


class _Deadman(threading.Thread):
    """Drop P2Lens to its safe value if no Keepalive arrives within
    DeadmanTimeout seconds.

    Same owner/decider split as RaspberryButton's DeadmanThread: the process
    that decides P2Lens may sit at its running value -- an AnalogInterlock
    watching the P2 cooling water -- is not this one. If that process is
    killed its keepalives stop, and this thread then does what P2lensOFF
    does, so the failure of the supervisor de-asserts by default.

    Disabled (DeadmanTimeout = 0) unless a device opts in, so every existing
    ElmitecLEEM2k instance is unaffected.
    """

    def __init__(self, ds):
        threading.Thread.__init__(self, name="ElmitecLEEM2k-deadman", daemon=True)
        self.ds = ds
        self.stop = threading.Event()

    def run(self):
        ds = self.ds
        period = min(0.5, ds.DeadmanTimeout / 4.0)
        try:
            while not self.stop.wait(period):
                if not ds._p2_asserted or ds._deadman_tripped:
                    continue
                idle = time.monotonic() - ds._last_keepalive
                if idle > ds.DeadmanTimeout:
                    ds.write_P2Lens(ds._p2lens_off)
                    ds._p2_asserted = False
                    ds._deadman_tripped = True
                    msg = ("Deadman expired: no Keepalive for %.1f s (timeout "
                           "%.1f s). P2Lens set to %g; P2lensON to restore."
                           % (idle, ds.DeadmanTimeout, ds._p2lens_off))
                    ds.set_status(msg)
                    ds.error_stream(msg)
        except Exception as exc:
            # A dead deadman must not look healthy.
            ds.set_state(tango.DevState.FAULT)
            ds.set_status("Deadman thread died: %s" % exc)
            ds.error_stream("Deadman thread died: %s" % exc)


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False
# PROTECTED REGION END #    //  ElmitecLEEM2k.additionnal_import

__all__ = ["ElmitecLEEM2k", "main"]


class ElmitecLEEM2k(Device):
    """
    Device server for accessing the settings of the LEEM2000 program from Elmitec.
    """
    # PROTECTED REGION ID(ElmitecLEEM2k.class_variable) ENABLED START #
    ElmitecLEEM2kConnected = False

    def TCPBlockingReceive(self):
        """One reply, up to the NUL that ends it, or ElmitecLEEM2kError.

        The old loop spun on `while ReceivedLength == 0: recv(1)`. On a blocking
        socket recv returns at least one byte, or zero only at end of file, so
        when LEEM2000 was restarted and the connection went away this
        turned into a busy loop at full CPU that never ended -- which is why
        the server had to be restarted by hand rather than recovering.
        """
        szData = ''
        while True:
            try:
                Bytereceived = self.s.recv(1)
            except OSError as e:
                self._drop("LEEM2000 stopped answering: %s" % e)
                raise ElmitecLEEM2kError("LEEM2000 stopped answering: %s" % e)
            if not Bytereceived:
                self._drop("LEEM2000 closed the connection")
                raise ElmitecLEEM2kError("LEEM2000 closed the connection")
            if Bytereceived == b'\x00':
                return szData
            # latin-1: LEEM2000 is a Windows program and sends the micro sign
            # (0xb5) in unit strings, which "ascii" rejected. latin-1 also maps
            # every single byte 1:1, so decoding recv(1) output can never split
            # a multibyte sequence.
            szData = szData + Bytereceived.decode("latin-1")

    def _send(self, data):
        """Send, and mark the link down if it fails so it gets rebuilt."""
        if not self.ElmitecLEEM2kConnected:
            raise ElmitecLEEM2kError("not connected to LEEM2000 at %s:%d"
                                  % (self.IP, self.Port))
        try:
            self.s.send(data)
        except OSError as e:
            self._drop("could not send to LEEM2000: %s" % e)
            raise ElmitecLEEM2kError("could not send to LEEM2000: %s" % e)

    def _drop(self, why):
        """Forget the connection; the reconnect thread will rebuild it."""
        self.ElmitecLEEM2kConnected = False
        try:
            self.s.close()
        except Exception:                                     # noqa: BLE001
            pass
        self.set_state(tango.DevState.FAULT)
        self.set_status(why)
        self.error_stream(why)

    def connect(self):
        """Open the link and start string mode. True if it is up.

        Everything past the connect() used to be outside the try, so a program
        that accepted the connection and then said nothing took the whole
        server down from init_device.

        Locked against write_P2Lens: connect() replaces self.s, and both the
        reconnect thread and the deadman thread call in from outside Tango's
        serialization monitor.
        """
        if self.ElmitecLEEM2kConnected:
            return True
        with self._io_lock:
            return self._connect_locked()

    def _connect_locked(self):
        try:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.settimeout(self.Timeout)
            self.s.connect((self.IP, self.Port))
            self.s.send(b'asc')          # start string communication
            self.ElmitecLEEM2kConnected = True     # TCPBlockingReceive needs it
            self.TCPBlockingReceive()
        except (ElmitecLEEM2kError, OSError) as e:
            self.ElmitecLEEM2kConnected = False
            try:
                self.s.close()
            except Exception:                                 # noqa: BLE001
                pass
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't connect to LEEM2000 at %s:%d: %s"
                            % (self.IP, self.Port, e))
            self.debug_stream("Can't connect to LEEM2000: %s" % e)
            return False
        self.set_state(tango.DevState.ON)
        self.set_status("Connected to LEEM2000 at %s:%d" % (self.IP, self.Port))
        self.debug_stream("Connected to LEEM2000")
        return True

    def disconnect(self):
        if self.ElmitecLEEM2kConnected:
            try:
                self.s.send(b'clo')
                self.s.close()
            except OSError as e:
                self.debug_stream("Untidy disconnect: %s" % e)
            self.ElmitecLEEM2kConnected = False
            self.debug_stream("Disconnected!")
    # PROTECTED REGION END #    //  ElmitecLEEM2k.class_variable

    # -----------------
    # Device Properties
    # -----------------

    IP = device_property(
        dtype='str', default_value="tvips.lab"
    )

    Port = device_property(
        dtype='uint16', default_value=5566
    )

    Timeout = device_property(
        dtype='float', default_value=5.0,
        doc='Seconds to wait on the socket. Without one, a program that is '
            'alive but silent blocked a read for ever.',
    )

    ReconnectPeriod = device_property(
        dtype='float', default_value=10.0,
        doc='Seconds between attempts to rebuild the link while it is down.',
    )

    DeadmanTimeout = device_property(
        dtype='double', default_value=0.0,
        doc='Seconds without a Keepalive command after which P2Lens is dropped '
            'to P2LensOffValue, as P2lensOFF would. 0 disables the deadman entirely '
            '(default). Set it comfortably above the restart time of whatever '
            'sends the keepalives -- an AnalogInterlock watching the P2 '
            'cooling water -- or restarting that server drops P2 every time.',
    )

    # ----------
    # Attributes
    # ----------

    Objective = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        standard_unit="mA",
    )

    Preset = attribute(
        dtype='str',
        access=AttrWriteType.READ_WRITE,
    )

    StartVoltage = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        standard_unit="V",
    )

    TransferLens = attribute(
        dtype='double',
        standard_unit="mA",
    )

    FieldLens = attribute(
        dtype='double',
        standard_unit="mA",
    )

    IntermLens = attribute(
        dtype='double',
        standard_unit="mA",
    )

    P1Lens = attribute(
        dtype='double',
        standard_unit="mA",
    )

    P2Lens = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        standard_unit="mA",
    )

    SampleTemperature = attribute(
        dtype='double',
        standard_unit="�C",
    )

    ChannelPlateVoltage = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        standard_unit="kV",
    )

    BombVoltage = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
    )

    IllDefX = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        unit="mA",
    )

    IllDefY = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        unit="mA",
    )

    IllEqX = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        unit="mA",
    )

    IllEqY = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        unit="mA",
    )

    ImEqX = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        unit="mA",
    )

    ImEqY = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        unit="mA",
    )

    P2LensOffValue = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=False,
        label="P2Lens OFF value",
        doc="The value P2lensOFF and the deadman drive P2Lens to -- the "
            "current the P2 lens can hold with no cooling water. Just a "
            "setpoint; writing it does not move the lens.",
    )

    P2LensOnValue = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=False,
        label="P2Lens ON value",
        doc="The value P2lensON drives P2Lens to -- the normal running "
            "current. Just a setpoint; writing it does not move the lens.",
    )

    TimeSinceKeepalive = attribute(
        dtype='double',
        label="TimeSinceKeepalive",
        unit="s",
        format="%4.1f",
        doc="Seconds since the last Keepalive (or P2lensON). Only meaningful "
            "with DeadmanTimeout set.",
    )

    DeadmanTripped = attribute(
        dtype='bool',
        label="DeadmanTripped",
        doc="True after the deadman dropped P2Lens for want of a Keepalive. "
            "Cleared by P2lensON.",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(ElmitecLEEM2k.init_device) ENABLED START #
        # connect() reports FAULT and returns rather than raising, so a
        # LEEM2000 that is not running no longer takes the server down.
        self._io_lock = threading.Lock()
        self.ElmitecLEEM2kConnected = False
        self._reconnect = None
        self._deadman = None
        # Deadman state. The setpoints get their real values from the
        # memorized attribute writes just after init_device; these are only
        # the fallback if nothing was ever stored.
        self._p2lens_off = 1400.0
        self._p2lens_on = 3650.0
        self._last_keepalive = time.monotonic()
        self._p2_asserted = False
        self._deadman_tripped = False
        self.connect()
        # And it keeps trying, so restarting LEEM2000 does not mean
        # restarting this server as well.
        self._reconnect = _Reconnect(self)
        self._reconnect.start()
        if self.DeadmanTimeout > 0.0:
            self._deadman = _Deadman(self)
            self._deadman.start()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.init_device
    def always_executed_hook(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  ElmitecLEEM2k.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.delete_device) ENABLED START #
        if (getattr(self, "_reconnect", None) is not None):
            self._reconnect.stop.set()
        if (getattr(self, "_deadman", None) is not None):
            self._deadman.stop.set()
        # Deliberately does NOT drop P2Lens: an Init from Jive must not
        # disturb a running experiment. If this server is gone for good the
        # deadman cannot help either -- it is the interlock dying that it
        # guards against, not this server.
        self.disconnect()
        self.set_state(tango.DevState.OFF)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.delete_device
    def read_Objective(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.Objective_read) ENABLED START #
        self._send(b"val 11")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.Objective_read

    def write_Objective(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.Objective_write) ENABLED START #
        self._send(("val 11 "+str(value)).encode("ascii"))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.Objective_write

    def read_Preset(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.Preset_read) ENABLED START #
        self._send(b"prl")
        data = self.TCPBlockingReceive()
        return data
        # PROTECTED REGION END #    //  ElmitecLEEM2k.Preset_read

    def write_Preset(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.Preset_write) ENABLED START #
        #self._send(("sep "+str(value)).encode("ascii"))
        #data = self.TCPBlockingReceive()
        #return data
        pass
        # PROTECTED REGION END #    //  ElmitecLEEM2k.Preset_write

    def read_StartVoltage(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.StartVoltage_read) ENABLED START #
        self._send(b"val 38")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.StartVoltage_read

    def write_StartVoltage(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.StartVoltage_write) ENABLED START #
        self._send(("val 38 "+str(value)).encode("ascii"))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.StartVoltage_write

    def read_TransferLens(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.TransferLens_read) ENABLED START #
        self._send(b"val 14")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.TransferLens_read

    def read_FieldLens(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.FieldLens_read) ENABLED START #
        self._send(b"val 19")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.FieldLens_read

    def read_IntermLens(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.IntermLens_read) ENABLED START #
        self._send(b"val 21")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IntermLens_read

    def read_P1Lens(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.P1Lens_read) ENABLED START #
        self._send(b"val 24")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.P1Lens_read

    def read_P2Lens(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.P2Lens_read) ENABLED START #
        self._send(b"val 27")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.P2Lens_read

    def write_P2Lens(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.P2Lens_write) ENABLED START #
        # Locked: the deadman thread calls in here from outside Tango's
        # serialization monitor, and connect() (reconnect thread) can be
        # replacing self.s at the same time.
        with self._io_lock:
            self._send(("val 27 "+str(value)).encode("ascii"))
            data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.P2Lens_write

    def read_P2LensOffValue(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.P2LensOffValue_read) ENABLED START #
        return self._p2lens_off
        # PROTECTED REGION END #    //  ElmitecLEEM2k.P2LensOffValue_read

    def write_P2LensOffValue(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.P2LensOffValue_write) ENABLED START #
        self._p2lens_off = float(value)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.P2LensOffValue_write

    def read_P2LensOnValue(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.P2LensON_read) ENABLED START #
        return self._p2lens_on
        # PROTECTED REGION END #    //  ElmitecLEEM2k.P2LensON_read

    def write_P2LensOnValue(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.P2LensON_write) ENABLED START #
        self._p2lens_on = float(value)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.P2LensON_write

    def read_TimeSinceKeepalive(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.TimeSinceKeepalive_read) ENABLED START #
        return time.monotonic() - self._last_keepalive
        # PROTECTED REGION END #    //  ElmitecLEEM2k.TimeSinceKeepalive_read

    def read_DeadmanTripped(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.DeadmanTripped_read) ENABLED START #
        return self._deadman_tripped
        # PROTECTED REGION END #    //  ElmitecLEEM2k.DeadmanTripped_read

    def read_SampleTemperature(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.SampleTemperature_read) ENABLED START #
        self._send(b"val 39")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.SampleTemperature_read

    def read_ChannelPlateVoltage(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.ChannelPlateVoltage_read) ENABLED START #
        self._send(b"val 105")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.ChannelPlateVoltage_read

    def write_ChannelPlateVoltage(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.ChannelPlateVoltage_write) ENABLED START #
        self._send(("val 105 "+str(value)).encode("ascii"))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.ChannelPlateVoltage_write

    def read_BombVoltage(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.BombVoltage_read) ENABLED START #
        self._send(b"val 41")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.BombVoltage_read

    def write_BombVoltage(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.BombVoltage_write) ENABLED START #
        self._send(("val 41 "+str(value)).encode("ascii"))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.BombVoltage_write

    def read_IllDefX(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllDefX_read) ENABLED START #
        self._send(b"val 2")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllDefX_read

    def write_IllDefX(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllDefX_write) ENABLED START #
        self._send(("val 2 "+str(value)).encode("ascii"))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllDefX_write

    def read_IllDefY(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllDefY_read) ENABLED START #
        self._send(b"val 3")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllDefY_read

    def write_IllDefY(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllDefY_write) ENABLED START #
        self._send(("val 3 "+str(value)).encode("ascii"))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllDefY_write

    def read_IllEqX(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllEqX_read) ENABLED START #
        self._send(b"val 30")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllEqX_read

    def write_IllEqX(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllEqX_write) ENABLED START #
        self._send(("val 30 "+str(value)).encode("ascii"))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllEqX_write

    def read_IllEqY(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllEqY_read) ENABLED START #
        self._send(b"val 31")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllEqY_read

    def write_IllEqY(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllEqY_write) ENABLED START #
        self._send(("val 31 "+str(value)).encode("ascii"))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllEqY_write

    def read_ImEqX(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.ImEqX_read) ENABLED START #
        self._send(b"val 33")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.ImEqX_read

    def write_ImEqX(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.ImEqX_write) ENABLED START #
        self._send(("val 33 "+str(value)).encode("ascii"))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.ImEqX_write

    def read_ImEqY(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.ImEqY_read) ENABLED START #
        self._send(b"val 34")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.ImEqY_read

    def write_ImEqY(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.ImEqY_write) ENABLED START #
        self._send(("val 34 "+str(value)).encode("ascii"))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.ImEqY_write


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
        # PROTECTED REGION ID(ElmitecLEEM2k.sendCommand) ENABLED START #
        self._send(argin.encode("ascii"))
        data = self.TCPBlockingReceive()
        return data
        # PROTECTED REGION END #    //  ElmitecLEEM2k.sendCommand

    @command
    @DebugIt()
    def P2lensOFF(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.P2lensOFF) ENABLED START #
        # Response to a P2 lens cooling-water cut: drop P2Lens to the value
        # the lens can hold without cooling. Also disarms the deadman -- P2 is
        # already at the safe value, nothing left to guard.
        self.write_P2Lens(self._p2lens_off)
        self._p2_asserted = False
        # PROTECTED REGION END #    //  ElmitecLEEM2k.P2lensOFF

    @command
    @DebugIt()
    def P2lensON(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.P2lensON) ENABLED START #
        # Put P2Lens back to its running value once the water is flowing
        # again. Also arms/refreshes the deadman and clears a trip: a P2lensON
        # by hand from Jive then persists only while something keeps sending
        # Keepalive, which is the point.
        self.write_P2Lens(self._p2lens_on)
        self._last_keepalive = time.monotonic()
        self._p2_asserted = True
        self._deadman_tripped = False
        # PROTECTED REGION END #    //  ElmitecLEEM2k.P2lensON

    @command
    @DebugIt()
    def Keepalive(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.Keepalive) ENABLED START #
        # Refreshes the deadman timer only. Never moves P2Lens: recovering
        # from a deadman trip needs an explicit P2lensON.
        self._last_keepalive = time.monotonic()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.Keepalive

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(ElmitecLEEM2k.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((ElmitecLEEM2k,), args=args, **kwargs)
    # PROTECTED REGION END #    //  ElmitecLEEM2k.main

if __name__ == '__main__':
    main()
