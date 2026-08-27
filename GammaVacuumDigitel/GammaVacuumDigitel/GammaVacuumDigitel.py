# -*- coding: utf-8 -*-
#
# This file is part of the GammaVacuumDigitel project
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""GammaVacuumDigitel

Device server for the Gamma Vacuum DIGITEL SPCe ion pump power supply.
Connects via Ethernet Telnet interface (TCP port 23).

Command format (Telnet):  spc <two-digit-hex-code> [data]
Response format:          <ADDR> <OK|ER> <CODE> [data...] <CHECKSUM><CR>
"""

# PyTango imports
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import device_property
from tango import DispLevel, DevState

# Additional imports
import socket
import os
import sys
import time

__all__ = ["GammaVacuumDigitel", "main"]

# Conversion factors from the device's pressure unit to mbar. MBA is what
# this controller actually reports; it was missing, and an unknown unit used
# to fall back to 1.0, which happened to be right for mbar and would have been
# a silent 1.33x error had the pump been switched to Torr. Unknown units are
# refused now instead of assumed.
_UNIT_TO_MBAR = {
    'MBA':  1.0,       # what the SPCe sends
    'MBAR': 1.0,       # what the QPC sends
    'MBR':  1.0,
    'mbar': 1.0,
    'Torr': 1.33322,
    'TOR':  1.33322,
    'PA':   0.01,
    'Pa':   0.01,
}


class DigitelError(Exception):
    """The controller did not answer, or answered something unusable.

    One exception for every way the exchange can fail, because to every caller
    they mean the same thing: there is no reading to be had.
    """

# What the controller sends instead of a reading when the high voltage is off
# (manual, commands 0A and 0B). Compared as the literal text it sends, so no
# float rounding can turn a sentinel into a plausible reading. These were
# defined before and used nowhere: an HV-off pump reported 1e-11 mbar, which
# reads as an outstanding vacuum.
_HV_OFF_CURRENT  = "0.1E-09"
_HV_OFF_PRESSURE = "0.1E-10"

# The same literal again, in the setpoint's Off Point, where it means
# something else: the manual says an Off Point of 0.1e-10 "will be ignored,
# and once the Setpoint is active, the Setpoint will remain active independent
# of the pressure thereafter". A marker, not a pressure.
_SETPOINT_LATCHES = "0.1E-10"

# The QPC will not take commands back to back. Measured against XPSIonPump.lab:
# 30 reads with no gap gave 24 timeouts in 252 s; the same 30 with 0.2 s between
# them gave none in 6.4 s. The SPCe tolerates back-to-back exchanges, so this
# costs it a little time and nothing else. A full sweep of the seven attributes
# is about 1.4 s.
_MIN_GAP = 0.2


class GammaVacuumDigitel(Device):
    """
    Device server for a Gamma Vacuum DIGITEL ion pump power supply, over the
    Ethernet Telnet interface (default TCP port 23).

    Confirmed against two models of the family, which share the transport, the
    prompt, the framing and the command codes:

        SPCe  ("SPC2")          one pump,  pressure unit MBA
        QPC   ("DIGITEL QPC")   four pumps, pressure unit MBAR

    The difference that matters is the supply number: the QPC requires it on
    every command and the SPCe ignores it, so it is always sent. One Tango
    device per pump, selected by the Supply property.
    """

    # -----------------
    # Device Properties
    # -----------------

    IP = device_property(
        dtype='str',
        doc='IP address or hostname of the controller. No default: it must '
            'be set in the Tango database when the device is registered.',
    )

    Port = device_property(
        dtype='int',
        default_value=23,
        doc='TCP port for the Telnet interface (default 23)',
    )

    Supply = device_property(
        dtype='int',
        default_value=1,
        doc='Which pump on the controller this device is. The QPC has four '
            'and requires the number on every command; the SPCe has one and '
            'ignores it, so 1 is right for a single-pump supply. One Tango '
            'device per pump.',
    )

    # ----------
    # Attributes
    # ----------

    Pressure = attribute(
        dtype='double',
        unit="mbar",
        standard_unit="mbar",
        display_unit="mbar",
        format="%4.2e",
        doc="Ion pump pressure in mbar (converted from device units)",
    )

    Current = attribute(
        dtype='double',
        unit="A",
        standard_unit="A",
        display_unit="A",
        format="%4.2e",
        doc="Ion pump current in Amperes",
    )

    Voltage = attribute(
        dtype='double',
        unit="V",
        standard_unit="V",
        display_unit="V",
        format="%6.0f",
        doc="Ion pump high voltage in Volts",
    )

    SupplyStatus = attribute(
        dtype='str',
        doc="Supply status message reported by the controller",
    )

    SetpointOn = attribute(
        dtype='double',
        unit="mbar",
        standard_unit="mbar",
        display_unit="mbar",
        format="%4.2e",
        doc="Pressure interlock On Point: the setpoint relay activates when "
            "the pressure is equal to or above this value",
    )

    SetpointActive = attribute(
        dtype='bool',
        doc="Whether the pressure interlock relay is currently active, as the "
            "controller reports it. INVALID on a supply that does not report "
            "it -- the SPCe answers only the two thresholds -- because "
            "deriving it from the pressure would be a guess: the relay latches "
            "once active and also turns on for error conditions",
    )

    SetpointOff = attribute(
        dtype='double',
        unit="mbar",
        standard_unit="mbar",
        display_unit="mbar",
        format="%4.2e",
        doc="Pressure interlock Off Point: the setpoint relay deactivates "
            "when the pressure is equal to or below this value. INVALID when "
            "it is the 0.1E-10 marker, which means the relay latches on "
            "instead of ever releasing",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        self._sock = None
        self._factor = None
        self._last = 0.0
        self._connect()

    def delete_device(self):
        self._disconnect()

    def always_executed_hook(self):
        pass

    # ------------------
    # Connection helpers
    # ------------------

    def _connect(self):
        """Open the TCP/Telnet connection and set initial device state.

        The pacing clock and the cached unit belong to the connection, so they
        are (re)set here rather than only in init_device: _send_command calls
        this itself whenever the socket has been dropped.
        """
        self._factor = None
        self._last = 0.0
        # None until asked: whether this supply reports the setpoint relay
        # state at all. Not knowing is different from it being absent.
        self._reports_relay = None
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(5.0)
            self._sock.connect((self.IP, self.Port))
            # Discard any Telnet negotiation bytes or welcome banner
            self._sock.settimeout(1.0)
            try:
                self._sock.recv(1024)
            except socket.timeout:
                pass
            self._sock.settimeout(5.0)
            # Query HV state to set the Tango state
            # Over Telnet the answer is "OK 00 YES"; parts[3] is the serial
            # layout's field and does not exist here, so this always fell
            # through to OFF -- the pump read RUNNING with its HV on and the
            # device server said OFF.
            if (self._fields('61')[:1] == ['YES']):
                self.set_state(DevState.ON)
            else:
                self.set_state(DevState.OFF)
            # Say what it is and what it can do. Both are one exchange each,
            # asked once, and they turn "why is SetpointActive always
            # invalid?" into something a client can read off the status.
            model = "unknown model"
            try:
                model = " ".join(self._fields('01')) or model
            except DigitelError:
                pass
            note = ""
            try:
                self._setpoint()
                if (not self._reports_relay):
                    note = ("; this supply reports only the two setpoint "
                            "thresholds, not the relay state, so "
                            "SetpointActive has no value to give")
            except DigitelError:
                pass
            self.set_status("Connected to %s at %s:%d, supply %d%s"
                            % (model, self.IP, self.Port, self.Supply, note))
            self._describe_relay_support()
        except Exception as e:
            self._sock = None
            self.set_state(DevState.FAULT)
            self.set_status("Connection failed: %s" % str(e))

    def _disconnect(self):
        self._factor = None
        self._reports_relay = None
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _send_command(self, cmd, data=None):
        """Send one Telnet command and return its reply, prompt removed.

        The controller ends a reply with CR CR LF and then its ">" prompt:

            spc 0b\\r\\n  ->  b'OK 00 2.2E-09 MBA\\r\\r\\n>'

        The old reader stopped at the first CR and then consumed exactly one
        more byte, leaving the rest in the socket. Every exchange after that
        returned the *previous* command's reply, with an empty read in
        between, and the lag grew by one on every call: asking six times for
        the pressure returned a voltage, nothing, a status, nothing, a
        pressure, nothing. Reading up to the prompt keeps the stream in step
        whatever the reply contains.
        """
        if self._sock is None:
            self._connect()
        if data is not None:
            msg = ("spc %s %s\r\n" % (cmd, data)).encode('ascii')
        else:
            msg = ("spc %s\r\n" % cmd).encode('ascii')
        try:
            # Anything still unread is the tail of an exchange that did not
            # check out; left there it would be read as this reply.
            self._sock.settimeout(0.0)
            try:
                while self._sock.recv(4096):
                    pass
            except (BlockingIOError, socket.timeout):
                pass
            # The controller needs a gap between exchanges; see _MIN_GAP.
            gap = _MIN_GAP - (time.monotonic() - self._last)
            if (gap > 0):
                time.sleep(gap)
            self._sock.settimeout(5.0)
            self._sock.sendall(msg)
            self._last = time.monotonic()
            response = b""
            while not response.endswith(b">"):
                c = self._sock.recv(1)
                if not c:
                    raise DigitelError("the controller closed the connection")
                if c == b'\xff':          # Telnet IAC: drop the two that follow
                    self._sock.recv(2)
                    continue
                response += c
            return response[:-1].decode('ascii').strip()
        except DigitelError:
            self._disconnect()
            raise
        except Exception as e:
            self._disconnect()
            raise DigitelError("communication error: %s" % e)

    def _fields(self, cmd, data=None):
        """The data fields of one reply, or DigitelError.

        The supply number goes on every command unless the caller passes
        something else. The QPC refuses a bare command with
        "ER 08 *ERROR: ILLEGAL FORMAT"; the SPCe accepts the number and
        ignores it, so one code path serves both.
        """
        if data is None:
            data = str(self.Supply)
        return self._checked(cmd, data)

    def _checked(self, cmd, data):
        """Send and validate one reply.

        Over Telnet the reply is  STATUS CODE [data...]. The manual is
        explicit that, unlike the serial link, "no opening tilde, no address
        field, and no checksum are required" -- but this server was written to
        the serial packet layout, so it read STATUS at parts[1] and the first
        data field at parts[3], one place to the right of where they are.
        """
        resp = self._send_command(cmd, data)
        parts = resp.split()
        if (len(parts) < 2):
            raise DigitelError("short reply to %s: %r" % (cmd, resp))
        if (parts[0] == 'ER'):
            raise DigitelError("the controller refused %s, error code %s"
                           % (cmd, parts[1]))
        if (parts[0] != 'OK'):
            raise DigitelError("reply to %s begins with neither OK nor ER: %r"
                           % (cmd, resp))
        fields = parts[2:]
        # A command it will not run still answers OK, with the complaint in
        # the data: "OK 00 *ERROR: COMMAND DISABLED".
        if (fields and fields[0].startswith('*ERROR')):
            raise DigitelError("the controller answered %s with %s"
                           % (cmd, ' '.join(fields)))
        return fields

    def _read_hv_state(self):
        """Set the state from what command 61 reports, not from what was asked.

        On and Off used to set the state themselves, so a command the
        controller did not carry out left the state describing the request
        rather than the pump.
        """
        try:
            on = (self._fields('61')[:1] == ['YES'])
        except DigitelError as e:
            self.set_state(DevState.FAULT)
            self.set_status("Can't tell whether the high voltage is on: %s" % e)
            self.error_stream("Can't tell whether the high voltage is on: %s" % e)
            return
        self.set_state(DevState.ON if on else DevState.OFF)
        self.set_status("Connected to SPCe at %s:%d, high voltage %s"
                        % (self.IP, self.Port, "on" if on else "off"))

    def _no_reading(self, what, why):
        """FAULT with the reason, and an INVALID value rather than a number.

        A made-up pressure or current is worse than none: read as a real
        measurement it says the pump is fine at the moment nothing is known.
        Same reasoning as LeyboldIG3 and CenterOneGauge.
        """
        self.set_state(DevState.FAULT)
        self.set_status("Can't read the %s: %s" % (what, why))
        self.error_stream("Can't read the %s: %s" % (what, why))
        return (0.0, time.time(), tango.AttrQuality.ATTR_INVALID)

    # ------------------
    # Attributes methods
    # ------------------

    def read_Pressure(self):
        # "OK 00 2.2E-09 MBA". The manual documents the unit as Torr, MBR or
        # PA; this controller actually sends MBA, which was in neither the
        # manual nor the table, and an unknown unit used to be assumed to be
        # mbar.
        try:
            fields = self._fields('0b')
            if (len(fields) < 2):
                raise DigitelError("pressure reply carries no unit: %r" % fields)
            if (fields[0].upper() == _HV_OFF_PRESSURE):
                raise DigitelError("the high voltage is off, so %s is the "
                                "HV-off marker and not a pressure" % fields[0])
            self._factor = self._unit_factor(fields[1])
            return float(fields[0]) * self._factor
        except (DigitelError, ValueError) as e:
            return self._no_reading("pressure", e)

    def read_Current(self):
        # "OK 00 7.9E-07 AMPS"
        try:
            fields = self._fields('0a')
            if (not fields):
                raise DigitelError("current reply carries no value")
            if (fields[0].upper() == _HV_OFF_CURRENT):
                raise DigitelError("the high voltage is off, so %s is the "
                                "HV-off marker and not a current" % fields[0])
            return float(fields[0])
        except (DigitelError, ValueError) as e:
            return self._no_reading("current", e)

    def read_Voltage(self):
        # "OK 00 -3500"
        try:
            fields = self._fields('0c')
            if (not fields):
                raise DigitelError("voltage reply carries no value")
            return float(fields[0])
        except (DigitelError, ValueError) as e:
            return self._no_reading("voltage", e)

    def read_SupplyStatus(self):
        # "OK 00 RUNNING", and the message can be several words. The old code
        # joined parts[3:-1], dropping the last word to skip a checksum that
        # the Telnet reply does not carry.
        try:
            return ' '.join(self._fields('0d'))
        except DigitelError as e:
            self.set_state(DevState.FAULT)
            self.set_status("Can't read the supply status: %s" % e)
            self.error_stream("Can't read the supply status: %s" % e)
            return ('', time.time(), tango.AttrQuality.ATTR_INVALID)

    def _unit_factor(self, unit):
        """The conversion to mbar of the unit the controller just reported."""
        if (unit not in _UNIT_TO_MBAR):
            raise DigitelError("unknown pressure unit %r: refusing to guess "
                               "the conversion to mbar" % unit)
        return _UNIT_TO_MBAR[unit]

    def _pressure_factor(self):
        """The conversion to mbar of whatever unit this supply is set to.

        There is no command that reports the unit on its own: 0B is the only
        place it appears, and 0E only sets it. The setpoint values carry no
        unit of their own, so they are in whatever 0B reports -- which meant
        reading the pressure and throwing it away on every setpoint access,
        doubling the traffic to the controller. It is remembered instead, and
        forgotten on reconnect; changing the unit needs an Init anyway.
        """
        if (self._factor is None):
            fields = self._fields('0b')
            if (len(fields) < 2):
                raise DigitelError("pressure reply carries no unit: %r"
                                   % fields)
            self._factor = self._unit_factor(fields[1])
        return self._factor
    def _setpoint(self):
        """(on, off, active) as strings; active is None when not reported.

        The same command answers in two shapes:

            SPCe:  OK 00 9.0E-08,2.0E-07              on, off
            QPC:   OK 00 1,1,5.0e-08,4.0e-07,1        number, enabled, on,
                                                      off, relay active

        The five-field form is the one the SPCe manual documents, and the SPCe
        is the model that does not send it. On a QPC the last field is the
        live interlock state, which is why SetpointActive exists.
        """
        raw = [f.strip() for f in ' '.join(self._fields('3c')).split(',')]
        if (len(raw) == 2):
            self._reports_relay = False
            return (raw[0], raw[1], None)
        if (len(raw) >= 5):
            self._reports_relay = True
            return (raw[2], raw[3], raw[4])
        raise DigitelError("setpoint reply is neither two nor five values: %r"
                           % raw)

    def read_SetpointActive(self):
        """The relay state, or INVALID on a supply that does not report it.

        A supply that answers only the two thresholds is not faulty and there
        is nothing wrong with the link: it simply has no such field to give,
        and it never will. That used to go through the same path as a failed
        exchange and put the whole device in FAULT, so reading one attribute a
        model cannot support made every other reading look suspect.

        Now the two are told apart. A capability that is absent returns
        INVALID and leaves the state alone; only a real failure faults.
        """
        try:
            (_on, _off, active) = self._setpoint()
        except (DigitelError, ValueError) as e:
            self.set_state(DevState.FAULT)
            self.set_status("Can't read the setpoint state: %s" % e)
            self.error_stream("Can't read the setpoint state: %s" % e)
            return (False, time.time(), tango.AttrQuality.ATTR_INVALID)
        if (active is None):
            # Not an error: no state change, no error_stream. The absence is
            # already in the device status and in this attribute's own
            # description, both set at connect.
            return (False, time.time(), tango.AttrQuality.ATTR_INVALID)
        return (active == '1')

    def _describe_relay_support(self):
        """Put the capability in the attribute's own description.

        So it is visible in Jive next to the attribute rather than only in the
        device status, and a client that finds SetpointActive permanently
        invalid can read why without asking anyone.
        """
        if (self._reports_relay is None):
            return
        try:
            attr = self.get_device_attr().get_attr_by_name("SetpointActive")
            cfg = attr.get_properties()
            if (self._reports_relay):
                cfg.description = ("Whether the pressure interlock relay is "
                                   "active, as the controller reports it")
            else:
                cfg.description = ("Not reported by this supply, which answers "
                                   "only the two setpoint thresholds. Always "
                                   "INVALID here; it is not a fault. Deriving "
                                   "it from the pressure would be a guess: the "
                                   "relay latches once active and also turns "
                                   "on for error conditions.")
            attr.set_properties(cfg)
        except Exception as e:                                # noqa: BLE001
            self.debug_stream("Could not describe SetpointActive: %s" % e)

    def read_SetpointOn(self):
        try:
            (on, _off, _active) = self._setpoint()
            return float(on) * self._pressure_factor()
        except (DigitelError, ValueError) as e:
            return self._no_reading("setpoint On Point", e)

    def read_SetpointOff(self):
        try:
            (_on, off, _active) = self._setpoint()
            if (off.upper() == _SETPOINT_LATCHES):
                raise DigitelError("the Off Point is the %s marker, so the relay "
                                "latches on instead of releasing: there is no "
                                "off pressure to report" % off)
            return float(off) * self._pressure_factor()
        except (DigitelError, ValueError) as e:
            return self._no_reading("setpoint Off Point", e)

    # --------
    # Commands
    # --------

    @command()
    @DebugIt()
    def On(self):
        """Enable high voltage (start ion pump)."""
        self._send_command('37', str(self.Supply))
        self._read_hv_state()

    @command()
    @DebugIt()
    def Off(self):
        """Disable high voltage (stop ion pump)."""
        self._send_command('38', str(self.Supply))
        self._read_hv_state()

    @command(
        dtype_in='str',
        dtype_out='str',
        display_level=DispLevel.EXPERT,
        doc_in='Two-digit hex command code, optionally followed by data (e.g. "0b" or "12 1200")',
        doc_out='Raw response string from the controller',
    )
    @DebugIt()
    def send_command(self, argin):
        """Send a raw SPCe command. Expert use only."""
        parts = argin.split(None, 1)
        cmd = parts[0]
        data = parts[1] if len(parts) > 1 else None
        try:
            return self._send_command(cmd, data)
        except DigitelError as e:
            tango.Except.throw_exception("SPCe_CommunicationFailed", str(e),
                                         "GammaVacuumDigitel.send_command")


# ----------
# Run server
# ----------

def main(args=None, **kwargs):
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((GammaVacuumDigitel,), args=args, **kwargs)

if __name__ == '__main__':
    main()
