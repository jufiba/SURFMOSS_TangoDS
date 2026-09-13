# -*- coding: utf-8 -*-
#
# This file is part of the Itech6000C project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" Itech6000C

ITech6000C control through ethernet socket.
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
# PROTECTED REGION ID(Itech6000C.additionnal_import) ENABLED START #
import os
import sys
import time
import socket
import threading

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


class _Deadman(threading.Thread):
    """Switch the output off if no Keepalive arrives within DeadmanTimeout.

    Same owner/decider split as FUGMCP's _Deadman and RaspberryButton's
    DeadmanThread: the process that decides this supply may hold current --
    an AnalogInterlock watching the cooling water of the VSM magnet -- is not
    this one. If that process is killed its keepalives stop, and this thread
    then does what OutputOff does, so the failure of the supervisor drops the
    output by default. Silence, not a message, is what triggers the
    protection: it is the only signal a dead process can still send.

    Disabled (DeadmanTimeout = 0) unless a device opts in, so an instance
    that nobody supervises is unaffected.
    """

    def __init__(self, ds):
        threading.Thread.__init__(self, name="Itech6000C-deadman", daemon=True)
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
                        ds._send(b"OUTPUT OFF\n")
                    except Exception as e:
                        ds.error_stream("Deadman could not switch the output "
                                        "off: %s" % e)
                    ds._output_asserted = False
                    ds._deadman_tripped = True
                    msg = ("Deadman expired: no Keepalive for %.1f s (timeout "
                           "%.1f s). Output switched off; OutputOn to restore."
                           % (idle, ds.DeadmanTimeout))
                    ds.set_state(tango.DevState.OFF)
                    ds.set_status(msg)
                    ds.error_stream(msg)
        except Exception as exc:
            # A dead deadman must not look healthy.
            ds.set_state(tango.DevState.FAULT)
            ds.set_status("Deadman thread died: %s" % exc)
            ds.error_stream("Deadman thread died: %s" % exc)

# PROTECTED REGION END #    //  Itech6000C.additionnal_import

__all__ = ["Itech6000C", "main"]


class Itech6000C(Device):
    """
    ITech6000C control through ethernet socket.
    """
    # PROTECTED REGION ID(Itech6000C.class_variable) ENABLED START #
    ItechConnected = False

    def TCPBlockingReceive(self):
        """One reply. Everything after the return was dead code -- the older
        byte-at-a-time loop, unreachable behind it -- and it is gone."""
        return self.s.recv(1024).decode("ascii")

    def _send(self, cmd):
        """One locked write, for a command that draws no reply.

        Every socket use goes through here or _ask. The deadman thread calls
        in from outside Tango's serialization monitor, so without this its
        "OUTPUT OFF" could interleave with a client's half-finished query and
        both would read the wrong answer -- on the supply that feeds the
        magnet. Raises a Tango error if the socket is not open, rather than
        sending on a socket that never connected.
        """
        with self._io_lock:
            if not self.ItechConnected:
                tango.Except.throw_exception(
                    "Itech6000C_NotConnected",
                    "no link to the Itech6000C at %s:%d" % (self.IP, self.Port),
                    "Itech6000C._send")
            self.s.send(cmd)

    def _ask(self, cmd):
        """One locked exchange: write, then read the reply. See _send."""
        with self._io_lock:
            if not self.ItechConnected:
                tango.Except.throw_exception(
                    "Itech6000C_NotConnected",
                    "no link to the Itech6000C at %s:%d" % (self.IP, self.Port),
                    "Itech6000C._ask")
            self.s.send(cmd)
            return self.TCPBlockingReceive()

    # The three bodies below are kept out of their @command wrappers so they
    # can be exercised without a Tango logger, as AnalogInterlock's do_bypass
    # and do_arm are.

    def do_output_on(self):
        self._send(b"OUTPUT ON\n")
        # Arms the deadman and clears a previous trip: recovering from one is
        # an explicit act, never something a Keepalive does on its own.
        self._last_keepalive = time.monotonic()
        self._output_asserted = True
        self._deadman_tripped = False
        self.set_state(tango.DevState.ON)

    def do_output_off(self):
        self._send(b"OUTPUT OFF\n")
        self._output_asserted = False
        self.set_state(tango.DevState.OFF)

    def do_keepalive(self):
        """Refresh the deadman timer, and nothing else. Never touches the
        output: recovering from a deadman trip needs an explicit OutputOn. An
        AnalogInterlock holding the permissive sends this every cycle."""
        self._last_keepalive = time.monotonic()

    def connect(self):
        """Open the link. True if it is up, so the caller can stop."""
        if self.ItechConnected:
            return True
        try:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.settimeout(self.Timeout)
            self.s.connect((self.IP, self.Port))
        except OSError as e:
            self.ItechConnected = False
            try:
                self.s.close()
            except Exception:                                 # noqa: BLE001
                pass
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't connect to Itech6000C at %s:%d: %s"
                            % (self.IP, self.Port, e))
            self.debug_stream("Can't connect to Itech6000C: %s" % e)
            return False
        self.ItechConnected = True
        self.set_status("Connected to Itech6000C at %s:%d" % (self.IP, self.Port))
        self.debug_stream("Connected to Itech6000C")
        return True

    def disconnect(self):
        if self.ItechConnected:
            self.s.close()
            self.ItechConnected = False
            self.debug_stream("Disconnected!")
   
    # PROTECTED REGION END #    //  Itech6000C.class_variable

    # -----------------
    # Device Properties
    # -----------------

    IP = device_property(
        dtype='str', default_value="PWSItech6000VSM.lab"
    )

    Port = device_property(
        dtype='uint', default_value=30000
    )

    Timeout = device_property(
        dtype='float', default_value=5.0,
        doc='Seconds to wait on the socket. Without one, a supply that is '
            'reachable but silent blocks a read for ever.',
    )

    DeadmanTimeout = device_property(
        dtype='double', default_value=0.0,
        doc='Seconds without a Keepalive command after which the output is '
            'switched off, as OutputOff would. 0 disables the deadman '
            '(default). Set it comfortably above the restart time of whatever '
            'sends the keepalives -- an AnalogInterlock watching the cooling '
            'water of the VSM magnet -- or a routine restart of that server '
            'drops the output on its own.',
    )

    # ----------
    # Attributes
    # ----------

    Current = attribute(
        dtype='double',
        label="Current",
        unit="A",
    )

    Voltage = attribute(
        dtype='double',
    )

    Power = attribute(
        dtype='double',
        label="Power",
        unit="W",
    )

    SetVoltage = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
    )

    SetCurrent = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
    )

    Identification = attribute(
        dtype='str',
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
        doc="True after the deadman switched the output off for want of a "
            "Keepalive. Cleared by OutputOn.",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(Itech6000C.init_device) ENABLED START #
        # An exception escaping init_device makes PyTango exit the whole
        # server. connect() used to report FAULT and return, and then this went
        # on to send on a socket that had never connected. FAULT here means the
        # supply cannot be reached; OFF below means it answered and its output
        # is off, which is a different fact.
        self._io_lock = threading.Lock()
        self._deadman = None
        self._last_keepalive = time.monotonic()
        self._output_asserted = False
        self._deadman_tripped = False
        if (not self.connect()):
            return
        try:
            data = self._ask(b"OUTPUT?\n")
        except OSError as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Itech6000C at %s:%d accepted the connection and "
                            "then stopped answering: %s" % (self.IP, self.Port, e))
            self.error_stream("Itech6000C stopped answering: %s" % e)
            return
        self.debug_stream("OUTPUT? -> %r" % data)
        if (not data):
            # data[0] on the empty string a silent supply returns was an
            # IndexError, and it took the server with it.
            self.set_state(tango.DevState.FAULT)
            self.set_status("Itech6000C at %s:%d answered OUTPUT? with nothing"
                            % (self.IP, self.Port))
            self.error_stream("Empty answer to OUTPUT?")
        elif (data[0]=="1"):
            self.set_state(tango.DevState.ON)
            self._output_asserted = True
        else:
            self.set_state(tango.DevState.OFF)
        # The deadman is armed from what the supply says it is doing, not from
        # what anyone asked for: coming up with the output already on is the
        # case that needs guarding, not the one that can be ignored.
        if self.DeadmanTimeout > 0.0:
            self._deadman = _Deadman(self)
            self._deadman.start()
        # PROTECTED REGION END #    //  Itech6000C.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(Itech6000C.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  Itech6000C.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(Itech6000C.delete_device) ENABLED START #
        if (getattr(self, "_deadman", None) is not None):
            self._deadman.stop.set()
        # Deliberately does NOT switch the output off: an Init from Jive must
        # not drop a running magnet. If this server is gone for good the
        # deadman cannot help either -- what it guards against is the
        # interlock dying, not this server.
        self.disconnect()
        # PROTECTED REGION END #    //  Itech6000C.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Current(self):
        # PROTECTED REGION ID(Itech6000C.Current_read) ENABLED START #
        return float(self._ask(b"MEASure:SCALar:CURRent:DC?\n"))
        # PROTECTED REGION END #    //  Itech6000C.Current_read

    def read_Voltage(self):
        # PROTECTED REGION ID(Itech6000C.Voltage_read) ENABLED START #
        return float(self._ask(b"MEASure:SCALar:VOLTAGE:DC?\n"))
        # PROTECTED REGION END #    //  Itech6000C.Voltage_read

    def read_Power(self):
        # PROTECTED REGION ID(Itech6000C.Power_read) ENABLED START #
        return float(self._ask(b"MEASure:SCALar:POWER:DC?\n"))
        # PROTECTED REGION END #    //  Itech6000C.Power_read

    def read_SetVoltage(self):
        # PROTECTED REGION ID(Itech6000C.SetVoltage_read) ENABLED START #
        return float(self._ask(b"SOURce:VOLTAGE:LEVel:IMMediate:AMPLitude?\n"))
        # PROTECTED REGION END #    //  Itech6000C.SetVoltage_read

    def write_SetVoltage(self, value):
        # PROTECTED REGION ID(Itech6000C.SetVoltage_write) ENABLED START #
        self._send(("SOURce:VOLTAGE:LEVel:IMMediate:AMPLitude %f\n"%(value)).encode("ascii"))
        # PROTECTED REGION END #    //  Itech6000C.SetVoltage_write

    def read_SetCurrent(self):
        # PROTECTED REGION ID(Itech6000C.SetCurrent_read) ENABLED START #
        return float(self._ask(b"SOURce:CURRENT:LEVel:IMMediate:AMPLitude?\n"))
        # PROTECTED REGION END #    //  Itech6000C.SetCurrent_read

    def write_SetCurrent(self, value):
        # PROTECTED REGION ID(Itech6000C.SetCurrent_write) ENABLED START #
        self._send(("SOURce:CURRENT:LEVel:IMMediate:AMPLitude %f\n"%(value)).encode("ascii"))
        # PROTECTED REGION END #    //  Itech6000C.SetCurrent_write

    def read_Identification(self):
        # PROTECTED REGION ID(Itech6000C.Identification_read) ENABLED START #
        return self._ask(b"SYST:VERS?\n")
        # PROTECTED REGION END #    //  Itech6000C.Identification_read

    def read_TimeSinceKeepalive(self):
        # PROTECTED REGION ID(Itech6000C.TimeSinceKeepalive_read) ENABLED START #
        return time.monotonic() - self._last_keepalive
        # PROTECTED REGION END #    //  Itech6000C.TimeSinceKeepalive_read

    def read_DeadmanTripped(self):
        # PROTECTED REGION ID(Itech6000C.DeadmanTripped_read) ENABLED START #
        return self._deadman_tripped
        # PROTECTED REGION END #    //  Itech6000C.DeadmanTripped_read


    # --------
    # Commands
    # --------

    @command(
    dtype_in='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def sendCommand(self, argin):
        # PROTECTED REGION ID(Itech6000C.sendCommand) ENABLED START #
        self._send((argin+"\n").encode("ascii"))
        return
        # PROTECTED REGION END #    //  Itech6000C.sendCommand

    @command(
    )
    @DebugIt()
    def OutputOn(self):
        # PROTECTED REGION ID(Itech6000C.OutputOn) ENABLED START #
        return self.do_output_on()
        # PROTECTED REGION END #    //  Itech6000C.OutputOn

    @command(
    )
    @DebugIt()
    def OutputOff(self):
        # PROTECTED REGION ID(Itech6000C.OutputOff) ENABLED START #
        return self.do_output_off()
        # PROTECTED REGION END #    //  Itech6000C.OutputOff

    @command(
    )
    @DebugIt()
    def Keepalive(self):
        # PROTECTED REGION ID(Itech6000C.Keepalive) ENABLED START #
        return self.do_keepalive()
        # PROTECTED REGION END #    //  Itech6000C.Keepalive

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def SendQuery(self, argin):
        # PROTECTED REGION ID(Itech6000C.SendQuery) ENABLED START #
        return self._ask((argin+"\n").encode("ascii"))
        # PROTECTED REGION END #    //  Itech6000C.SendQuery

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(Itech6000C.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((Itech6000C,), args=args, **kwargs)
    # PROTECTED REGION END #    //  Itech6000C.main

if __name__ == '__main__':
    main()
