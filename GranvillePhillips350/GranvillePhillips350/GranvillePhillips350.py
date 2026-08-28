# -*- coding: utf-8 -*-
#
# This file is part of the GranvillePhillips350 project
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" GranvillePhillips350

Pressure from a Granville Phillips 350 ion gauge controller, over the RS-232
interface module.
"""

# PyTango imports
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import device_property
from tango import AttrQuality, DispLevel, DevState
# Additional import
import os
import sys
import time
import serial

__all__ = ["GranvillePhillips350", "main"]


class GP350Error(Exception):
    """The 350 did not answer, or answered something unusable.

    One exception for every way the exchange can fail, because to every caller
    they mean the same thing: there is no reading to be had.
    """


# What the 350 sends instead of a pressure when no filament is on, or during
# the first few seconds after one is switched on (manual, DS IG). It is not a
# reading, and at 9.9e9 it is not a pressure any vacuum system could reach, so
# anything absurdly large is treated as the marker rather than matching the
# exact text -- the manual prints it as both "9.90E+09" and "9.90E+9".
_GAUGE_OFF_ABOVE = 1.0e9

# The replies the 350 sends in place of a normal response when it could not
# read the message (manual, Error Messages). SYNTAX ERROR is also what it
# answers if DCD was not asserted while the message was being sent, which on a
# null modem cable is a wiring question rather than a software one.
_ERROR_REPLIES = ("SYNTAX ERROR", "OVERRUN ERROR", "PARITY ERROR")


class GranvillePhillips350(Device):
    """
    Granville Phillips 350 ion gauge controller, RS-232 interface module.

    The command set of that module is small and closed: DG, DGS, DS IG, IG1
    and IG2. Messages are upper-case ASCII terminated with CRLF, and every
    message gets a reply, also CRLF terminated, with numbers formatted
    X.XXE+-XX.

    Nothing in the protocol reports the byte framing or the pressure unit, so
    both are device properties:

    - Framing is set by DIP switches on the RS-232 board, and there is no way
      to ask the instrument what it is on. The LEEM one was measured at 9600
      7N2 on 28-Aug-2026 -- the factory framing, but at 9600 rather than the
      factory 300 -- and those are the defaults here.
      tools/gp350_probe.py finds the combination on any other.
    - The unit is set by a switch on the electrometer module and printed on
      the front panel label. The 350 sends a bare number, so the unit is
      whatever that label says. It is declared, not guessed.
    """

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str',
        doc='Serial port. No default: it must be set in the Tango database '
            'when the device is registered.',
    )

    Baudrate = device_property(
        dtype='int', default_value=9600,
        doc='DIP switches S6-S8 on the RS-232 board select 75 to 9600. The '
            'factory default is 300; the LEEM instrument was measured at 9600 '
            'on 28-Aug-2026 and that is what this defaults to, so a device '
            'registered without setting it works on that one.',
    )

    Bytesize = device_property(
        dtype='int', default_value=7,
        doc='7 or 8, from DIP switches S3-S5. Factory default 7, and what the '
            'LEEM instrument was measured at.',
    )

    Parity = device_property(
        dtype='str', default_value='N',
        doc="'N', 'E' or 'O', from DIP switches S3-S5. Factory default N.",
    )

    Stopbits = device_property(
        dtype='int', default_value=2,
        doc='1 or 2, from DIP switches S3-S5. Factory default 2, and what the '
            'LEEM instrument was measured at.',
    )

    PressureUnit = device_property(
        dtype='str', default_value='Torr',
        doc='The unit the electrometer module is switched to, as printed on '
            'the front panel label. The 350 sends a bare number and cannot be '
            'asked, so this is only a label: it is not converted.',
    )

    Timeout = device_property(
        dtype='float', default_value=3.0,
        doc='Seconds to wait for a reply. Generous by default because at 300 '
            'baud a reply takes an appreciable fraction of a second.',
    )

    # ----------
    # Attributes
    # ----------

    Pressure = attribute(
        dtype='double',
        label="Pressure",
        unit="Torr",
        format="%4.2e",
        doc="Ion gauge pressure, in whatever unit PressureUnit names. INVALID "
            "when no filament is on: the 350 answers 9.90E+09 then, which is "
            "a marker and not a reading.",
    )

    Filament1On = attribute(
        dtype='bool',
        doc="Whether filament 1 is on, from DS IG1 answering a pressure "
            "rather than the gauge-off marker",
    )

    Filament2On = attribute(
        dtype='bool',
        doc="Whether filament 2 is on, from DS IG2",
    )

    DegasOn = attribute(
        dtype='bool',
        doc="Whether electron bombardment degas is running (DGS)",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # An exception escaping init_device makes PyTango exit the whole
        # server, and the Starter then leaves it for dead. Everything that can
        # fail is caught and turned into FAULT with the reason in the status.
        self.ser = None
        try:
            self.ser = serial.Serial(
                self.SerialPort,
                baudrate=self.Baudrate,
                bytesize=self.Bytesize,
                parity=self.Parity,
                stopbits=self.Stopbits,
                timeout=self.Timeout,
            )
        except (serial.SerialException, ValueError) as e:
            self.set_state(DevState.FAULT)
            self.set_status("Can't open %s: %s" % (self.SerialPort, e))
            self.error_stream("Can't open %s: %s" % (self.SerialPort, e))
            return
        # The declared unit is only a label; make it say what the front panel
        # says rather than the value this file happens to have been written
        # with. Wrapped because a client should not lose the device over it.
        try:
            attr = self.get_device_attr().get_attr_by_name("Pressure")
            cfg = attr.get_properties()
            cfg.unit = self.PressureUnit
            attr.set_properties(cfg)
        except Exception as e:                                # noqa: BLE001
            self.debug_stream("Could not relabel the Pressure unit: %s" % e)
        try:
            self._ask("DGS")
        except GP350Error as e:
            self.set_state(DevState.FAULT)
            self.set_status("No usable answer on %s: %s" % (self.SerialPort, e))
            self.error_stream("No usable answer on %s: %s" % (self.SerialPort, e))
            return
        self.set_state(DevState.ON)

    def delete_device(self):
        if (self.ser is not None):
            self.ser.close()

    def always_executed_hook(self):
        pass

    # ------------------
    # Protocol
    # ------------------

    def _ask(self, message):
        """Send one message and return its reply, or raise GP350Error.

        The 350 answers every message. Replies end CRLF; the terminator it
        expects on the way in may be CRLF or a bare LF, so LF is what is read
        for and any CR is stripped afterwards.

        The input buffer is cleared before writing. That matters more here
        than on a command/response bus: with switch S1 off at power-up the
        module runs in talk-only mode and sends all three displays every five
        seconds unasked, so there can be a line waiting that answers nothing.
        """
        if (self.ser is None):
            raise GP350Error("the serial port is not open")
        self.ser.reset_input_buffer()
        self.ser.write((message + "\r\n").encode("ascii"))
        reply = self.ser.read_until(b"\n").decode("ascii", "replace").strip()
        if (not reply):
            raise GP350Error("no reply to %r (timeout, cable, or the wrong "
                             "baud rate or byte framing)" % message)
        if (reply in _ERROR_REPLIES):
            raise GP350Error("the 350 answered %r with %s" % (message, reply))
        return reply

    def _pressure(self, message):
        """The pressure DS IG / DS IG1 / DS IG2 reports, or None if gauge off.

        Raises GP350Error if the answer is not a number at all.
        """
        reply = self._ask(message)
        try:
            value = float(reply)
        except ValueError:
            raise GP350Error("the answer to %r is not a number: %r"
                             % (message, reply))
        if (value >= _GAUGE_OFF_ABOVE):
            return None
        return value

    def _no_reading(self, what, why):
        """FAULT with the reason, and INVALID rather than an invented number.

        0.0 on a pressure gauge reads as perfect vacuum, which is the most
        dangerous value this attribute can hand to an interlock or an alarm:
        it says the chamber is fine at exactly the moment nothing is known.
        Same reasoning as LeyboldIG3 and CenterOneGauge.
        """
        self.set_state(DevState.FAULT)
        self.set_status("Can't read the %s: %s" % (what, why))
        self.error_stream("Can't read the %s: %s" % (what, why))
        return (0.0, time.time(), AttrQuality.ATTR_INVALID)

    # ------------------
    # Attributes methods
    # ------------------

    def read_Pressure(self):
        try:
            value = self._pressure("DS IG")
        except GP350Error as e:
            return self._no_reading("pressure", e)
        if (value is None):
            # Not a fault: the gauge is simply off, or still starting. Saying
            # OFF and INVALID is the truth; a number here would not be.
            self.set_state(DevState.OFF)
            self.set_status("No filament is on, so there is no pressure to "
                            "report (the 350 answers its gauge-off marker)")
            return (0.0, time.time(), AttrQuality.ATTR_INVALID)
        self.set_state(DevState.ON)
        self.set_status("The device is in ON state.")
        return value

    def read_Filament1On(self):
        return self._filament("DS IG1", "filament 1")

    def read_Filament2On(self):
        return self._filament("DS IG2", "filament 2")

    def _filament(self, message, what):
        try:
            return self._pressure(message) is not None
        except GP350Error as e:
            self.set_state(DevState.FAULT)
            self.set_status("Can't read %s: %s" % (what, e))
            self.error_stream("Can't read %s: %s" % (what, e))
            return (False, time.time(), AttrQuality.ATTR_INVALID)

    def read_DegasOn(self):
        try:
            reply = self._ask("DGS")
        except GP350Error as e:
            self.set_state(DevState.FAULT)
            self.set_status("Can't read the degas status: %s" % e)
            self.error_stream("Can't read the degas status: %s" % e)
            return (False, time.time(), AttrQuality.ATTR_INVALID)
        if (reply not in ("0", "1")):
            self.set_state(DevState.FAULT)
            self.set_status("DGS answered %r, which is neither 0 nor 1" % reply)
            self.error_stream("DGS answered %r" % reply)
            return (False, time.time(), AttrQuality.ATTR_INVALID)
        return (reply == "1")

    # --------
    # Commands
    # --------

    def _accepted(self, message):
        """Send a control message; the 350 answers OK or INVALID."""
        reply = self._ask(message)
        if (reply == "OK"):
            return
        if (reply == "INVALID"):
            tango.Except.throw_exception(
                "GP350_Rejected",
                "The 350 rejected %r. It answers INVALID when the request "
                "makes no sense in its current state -- switching on a "
                "filament that is already on, or degassing with no filament "
                "running." % message,
                "GranvillePhillips350.%s" % message.replace(" ", "_"))
        tango.Except.throw_exception(
            "GP350_BadReply", "The 350 answered %r with %r" % (message, reply),
            "GranvillePhillips350.%s" % message.replace(" ", "_"))

    @command()
    @DebugIt()
    def StartFilament1(self):
        """Switch filament 1 on.

        OK means only that the request reached the electrometer: the tube can
        still fail to light, at too high a pressure or if it is disconnected.
        Read Filament1On afterwards to see whether it actually came on.
        """
        self._accepted("IG1 ON")

    @command()
    @DebugIt()
    def StopFilament1(self):
        """Switch filament 1 off."""
        self._accepted("IG1 OFF")

    @command()
    @DebugIt()
    def StartFilament2(self):
        """Switch filament 2 on. See StartFilament1."""
        self._accepted("IG2 ON")

    @command()
    @DebugIt()
    def StopFilament2(self):
        """Switch filament 2 off."""
        self._accepted("IG2 OFF")

    @command()
    @DebugIt()
    def DegasStart(self):
        """Start electron bombardment degas.

        The manual is explicit that OK only means the request was sent, and
        that degas will not start above 5e-5 Torr. Read DegasOn to find out
        whether it did.
        """
        self._accepted("DG ON")

    @command()
    @DebugIt()
    def DegasStop(self):
        """Stop degas."""
        self._accepted("DG OFF")

    @command(
        dtype_in='str',
        dtype_out='str',
        display_level=DispLevel.EXPERT,
        doc_in='A raw 350 message, e.g. "DS IG" or "DGS". Upper case.',
        doc_out='The reply, with its terminator stripped',
    )
    @DebugIt()
    def sendCommand(self, argin):
        """Send a raw message. Expert use only."""
        try:
            return self._ask(argin)
        except GP350Error as e:
            tango.Except.throw_exception(
                "GP350_CommunicationFailed", str(e),
                "GranvillePhillips350.sendCommand")


# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((GranvillePhillips350,), args=args, **kwargs)


if __name__ == '__main__':
    main()
