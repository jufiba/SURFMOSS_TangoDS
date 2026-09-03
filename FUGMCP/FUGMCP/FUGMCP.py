# -*- coding: utf-8 -*-
#
# This file is part of the FUGMCP project
#
# GPL 2
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" 

Device server for the HV power supply MCP 140-1250 (1250V, 100mA). It has a USB module for digital interfacing, Probus V.
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
# PROTECTED REGION ID(FUGMCP.additionnal_import) ENABLED START #
import os
import sys
import time
import threading
import serial


class _Deadman(threading.Thread):
    """Switch the HV output off if no Keepalive arrives within DeadmanTimeout.

    Same owner/decider split as RaspberryButton's DeadmanThread: the process
    that decides the supply may hold HV -- an AnalogInterlock watching the
    cooling water of a water-jacketed MBE evaporator -- is not this one. If
    that process is killed its keepalives stop, and this thread then does what
    OutputOff does, so the failure of the supervisor drops the HV by default.

    Disabled (DeadmanTimeout = 0) unless a device opts in, so every existing
    FUGMCP instance is unaffected.
    """

    def __init__(self, ds):
        threading.Thread.__init__(self, name="FUGMCP-deadman", daemon=True)
        self.ds = ds
        self.stop = threading.Event()

    def run(self):
        ds = self.ds
        period = min(0.5, ds.DeadmanTimeout / 4.0)
        try:
            while not self.stop.wait(period):
                if not ds._output_asserted or ds._deadman_tripped:
                    continue
                idle = time.monotonic() - ds._last_keepalive
                if idle > ds.DeadmanTimeout:
                    try:
                        ds._txn(b">BON 0\n")
                    except Exception as e:
                        ds.error_stream("Deadman could not switch HV off: %s" % e)
                    ds._output_asserted = False
                    ds._deadman_tripped = True
                    msg = ("Deadman expired: no Keepalive for %.1f s (timeout "
                           "%.1f s). HV output switched off; OutputOn to restore."
                           % (idle, ds.DeadmanTimeout))
                    ds.set_state(tango.DevState.OFF)
                    ds.set_status(msg)
                    ds.error_stream(msg)
        except Exception as exc:
            # A dead deadman must not look healthy.
            ds.set_state(tango.DevState.FAULT)
            ds.set_status("Deadman thread died: %s" % exc)
            ds.error_stream("Deadman thread died: %s" % exc)
# PROTECTED REGION END #    //  FUGMCP.additionnal_import

__all__ = ["FUGMCP", "main"]


class FUGMCP(Device):
    """
    Device server for the HV power supply MCP 140-1250 (1250V, 100mA). It has a USB module for digital interfacing, Probus V.
    """
    # PROTECTED REGION ID(FUGMCP.class_variable) ENABLED START #
    ser = None

    def _txn(self, cmd):
        """One locked serial exchange: write, return one line. Raises a Tango
        error if the port is not open. The deadman thread calls in here from
        outside Tango's serialization monitor, so this is where its serial use
        is kept from interleaving with a client's."""
        with self._io_lock:
            if self.ser is None:
                tango.Except.throw_exception(
                    "FUGMCP_NotConnected",
                    "no serial link to the FUG MCP on %s" % self.SerialPort,
                    "FUGMCP._txn")
            self.ser.write(cmd)
            return self.ser.readline()
    # PROTECTED REGION END #    //  FUGMCP.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str', default_value="/dev/ttyUSB0"
    )

    Speed = device_property(
        dtype='int', default_value=625000
    )

    DeadmanTimeout = device_property(
        dtype='double', default_value=0.0,
        doc='Seconds without a Keepalive command after which the HV output is '
            'switched off, as OutputOff would. 0 disables the deadman '
            '(default). Set it comfortably above the restart time of whatever '
            'sends the keepalives -- an AnalogInterlock watching the cooling '
            'water of a water-jacketed evaporator.',
    )

    # ----------
    # Attributes
    # ----------

    Voltage = attribute(
        dtype='double',
        label="Voltage",
        unit="V",
        format="%5.1f",
        max_value=1250,
        min_value=0,
    )

    Current = attribute(
        dtype='double',
        label="Current",
        unit="A",
        format="%6.4f",
        max_value=0.100,
        min_value=0,
    )

    Power = attribute(
        dtype='double',
        label="Power",
        unit="W",
        format="%5.1f",
    )

    SetVoltage = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        unit="V",
        format="%5.1f",
        max_value=1250,
        min_value=0,
    )

    SetCurrent = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        label="SetCurrent",
        unit="A",
        format="%6.4f",
        max_value=100,
        min_value=0,
    )

    Identification = attribute(
        dtype='str',
        display_level=DispLevel.EXPERT,
    )

    CC = attribute(
        dtype='bool',
    )

    CV = attribute(
        dtype='bool',
    )

    TimeSinceKeepalive = attribute(
        dtype='double',
        unit="s",
        format="%4.1f",
        doc="Seconds since the last Keepalive (or OutputOn). Only meaningful "
            "with DeadmanTimeout set.",
    )

    DeadmanTripped = attribute(
        dtype='bool',
        doc="True after the deadman switched the HV off for want of a "
            "Keepalive. Cleared by OutputOn.",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(FUGMCP.init_device) ENABLED START #
        self._io_lock=threading.Lock()
        self.ser=None
        self._deadman=None
        self._last_keepalive=time.monotonic()
        self._output_asserted=False
        self._deadman_tripped=False
        try:
            self.ser=serial.Serial(port=self.SerialPort,baudrate=self.Speed,bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,stopbits=1,timeout=0.5)
            self.ser.write(bytes("*IDN?\n","ascii"))
            self.identification=self.ser.readline()
        except Exception as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't connect to FUG MCP on %s: %s"%(self.SerialPort,e))
            self.error_stream("Can't connect to FUG MCP on %s: %s"%(self.SerialPort,e))
            return
        if  (self.identification[0:16]!=bytes("FUG HCP 140-1250","ascii") and self.identification[0:15]!=bytes("FUG MCP140-1250","ascii")):
            self.set_state(tango.DevState.FAULT)
            self.set_status("I do not find a FUG MCP on the serial port")
            self.debug_stream("I do not find a FUG MCP on the serial port")
            return
        self.set_status("Connected to FUG MCP")
        self.debug_stream("Connected to FUG MCP")
        # Asking whether the output is on was outside any try. OFF here means
        # the output is disabled, which is the supply answering -- not the
        # supply being unreachable, which is FAULT above.
        try:
            self.ser.write(bytes(">BON?\n","ascii"))
            resp=self.ser.readline()
        except Exception as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("The FUG MCP identified itself and then stopped "
                            "answering on %s: %s"%(self.SerialPort,e))
            self.error_stream("FUG MCP stopped answering on %s: %s"%(self.SerialPort,e))
            return
        if (resp[:-1]==bytes("BON:1","ascii")):
            self.set_state(tango.DevState.ON)
            self._output_asserted=True
        else:
            self.set_state(tango.DevState.OFF)
        if self.DeadmanTimeout > 0.0:
            self._deadman=_Deadman(self)
            self._deadman.start()
        # PROTECTED REGION END #    //  FUGMCP.init_device
    def always_executed_hook(self):
        # PROTECTED REGION ID(FUGMCP.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  FUGMCP.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(FUGMCP.delete_device) ENABLED START #
        if (getattr(self, "_deadman", None) is not None):
            self._deadman.stop.set()
        # Deliberately does NOT switch the HV off: an Init from Jive must not
        # trip a running evaporation. If this server is gone for good the
        # deadman cannot help either -- it is the interlock dying that it
        # guards against, not this server.
        if (self.ser is not None):
            self.ser.close()
        # PROTECTED REGION END #    //  FUGMCP.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Voltage(self):
        # PROTECTED REGION ID(FUGMCP.Voltage_read) ENABLED START #
        resp=self._txn(b">M0 ?\n")
        return float(resp[3:-1])
        # PROTECTED REGION END #    //  FUGMCP.Voltage_read

    def read_Current(self):
        # PROTECTED REGION ID(FUGMCP.Current_read) ENABLED START #
        resp=self._txn(b">M1 ?\n")
        return float(resp[3:-1])
        # PROTECTED REGION END #    //  FUGMCP.Current_read

    def read_Power(self):
        # PROTECTED REGION ID(FUGMCP.Power_read) ENABLED START #
        v=float(self._txn(b">M0 ?\n")[3:-1])
        i=float(self._txn(b">M1 ?\n")[3:-1])
        return(v*i)
        # PROTECTED REGION END #    //  FUGMCP.Power_read

    def read_SetVoltage(self):
        # PROTECTED REGION ID(FUGMCP.SetVoltage_read) ENABLED START #
        resp=self._txn(b">S0 ?\n")
        return float(resp[3:-1])
        # PROTECTED REGION END #    //  FUGMCP.SetVoltage_read

    def write_SetVoltage(self, value):
        # PROTECTED REGION ID(FUGMCP.SetVoltage_write) ENABLED START #
        resp=self._txn((">S0 %f\n"%value).encode("ascii"))
        if (resp[:-1]!=bytes("E0","ascii")):
            self.set_state(tango.DevState.FAULT)
            # decode with "replace", not the strict decode used elsewhere
            # in this repository: this runs when the instrument answered
            # something unexpected, so the bytes may not be ASCII at all,
            # and a decode that raises would lose the one message that
            # says what went wrong.
            self.set_status("Error writing SetVoltage from FUG MCP %s"%resp[:-1].decode("ascii","replace"))
            self.debug_stream("Error writing SetVoltage from FUG MCP %s"%resp[:-1].decode("ascii","replace"))
        return
        # PROTECTED REGION END #    //  FUGMCP.SetVoltage_write

    def read_SetCurrent(self):
        # PROTECTED REGION ID(FUGMCP.SetCurrent_read) ENABLED START #
        resp=self._txn(b">S1 ?\n")
        return float(resp[3:-1])
        # PROTECTED REGION END #    //  FUGMCP.SetCurrent_read

    def write_SetCurrent(self, value):
        # PROTECTED REGION ID(FUGMCP.SetCurrent_write) ENABLED START #
        resp=self._txn((">S1 %f\n"%value).encode("ascii"))
        if (resp[:-1]!=bytes("E0","ascii")):
            self.set_state(tango.DevState.FAULT)
            self.set_status("Error writing SetCurret from FUG MCP %s"%resp[:-1].decode("ascii","replace"))
            self.debug_stream("Error writing SetCurrent from FUG MCP %s"%resp[:-1].decode("ascii","replace"))
        return
        # PROTECTED REGION END #    //  FUGMCP.SetCurrent_write

    def read_Identification(self):
        # PROTECTED REGION ID(FUGMCP.Identification_read) ENABLED START #
        return(self.identification.decode("ascii"))
        # PROTECTED REGION END #    //  FUGMCP.Identification_read

    def read_CC(self):
        # PROTECTED REGION ID(FUGMCP.CC_read) ENABLED START #
        resp=self._txn(b">DIR ?\n")
        if (resp[:-1]==bytes("DIR:1","ascii")):
            return(True)
        else:
            return(False)
        # PROTECTED REGION END #    //  FUGMCP.CC_read

    def read_CV(self):
        # PROTECTED REGION ID(FUGMCP.CV_read) ENABLED START #
        resp=self._txn(b">DVR ?\n")
        if (resp[:-1]==bytes("DVR:1","ascii")):
            return(True)
        else:
            return(False)
        # PROTECTED REGION END #    //  FUGMCP.CV_read

    def read_TimeSinceKeepalive(self):
        # PROTECTED REGION ID(FUGMCP.TimeSinceKeepalive_read) ENABLED START #
        return time.monotonic() - self._last_keepalive
        # PROTECTED REGION END #    //  FUGMCP.TimeSinceKeepalive_read

    def read_DeadmanTripped(self):
        # PROTECTED REGION ID(FUGMCP.DeadmanTripped_read) ENABLED START #
        return self._deadman_tripped
        # PROTECTED REGION END #    //  FUGMCP.DeadmanTripped_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def OutputOn(self):
        # PROTECTED REGION ID(FUGMCP.OutputOn) ENABLED START #
        resp=self._txn(b">BON 1\n")
        if (resp[:-1]!=b"E0"):
            self.set_state(tango.DevState.FAULT)
            return
        self._last_keepalive=time.monotonic()
        self._output_asserted=True
        self._deadman_tripped=False
        self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  FUGMCP.OutputOn

    @command(
    )
    @DebugIt()
    def OutputOff(self):
        # PROTECTED REGION ID(FUGMCP.OutputOff) ENABLED START #
        resp=self._txn(b">BON 0\n")
        self._output_asserted=False
        if (resp[:-1]!=b"E0"):
            self.set_state(tango.DevState.FAULT)
            return
        self.set_state(tango.DevState.OFF)
        # PROTECTED REGION END #    //  FUGMCP.OutputOff

    @command(
    )
    @DebugIt()
    def Keepalive(self):
        # PROTECTED REGION ID(FUGMCP.Keepalive) ENABLED START #
        # Refreshes the deadman timer only. Never touches the output:
        # recovering from a deadman trip needs an explicit OutputOn.
        self._last_keepalive=time.monotonic()
        # PROTECTED REGION END #    //  FUGMCP.Keepalive

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def sendCommand(self, argin):
        # PROTECTED REGION ID(FUGMCP.sendCommand) ENABLED START #
        result=self._txn((argin+"\n").encode("ascii"))
        return(result.decode("ascii","replace"))
        # PROTECTED REGION END #    //  FUGMCP.sendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(FUGMCP.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((FUGMCP,), args=args, **kwargs)
    # PROTECTED REGION END #    //  FUGMCP.main

if __name__ == '__main__':
    main()
