# -*- coding: utf-8 -*-
#
# This file is part of the GammaVacuumSPCe project
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""GammaVacuumSPCe

Device server for the Gamma Vacuum DIGITEL SPCe ion pump power supply.
Connects via Ethernet Telnet interface (TCP port 23).

Command format (Telnet):  spc <two-digit-hex-code> [data]
Response format:          <ADDR> <OK|ER> <CODE> [data...] <CHECKSUM><CR>
"""

# PyTango imports
import PyTango
from PyTango import DebugIt
from PyTango.server import run
from PyTango.server import Device, DeviceMeta
from PyTango.server import attribute, command
from PyTango.server import device_property
from PyTango import DispLevel, DevState

# Additional imports
import socket
import os
import sys

__all__ = ["GammaVacuumSPCe", "main"]

# Conversion factors from the device's pressure unit to mbar
_UNIT_TO_MBAR = {
    'Torr': 1.33322,
    'MBR':  1.0,
    'mbar': 1.0,
    'PA':   0.01,
    'Pa':   0.01,
}

# Sentinel values returned when HV is off
_HV_OFF_CURRENT  = 0.1e-9   # "0.1E-09 AMPS" = HV off
_HV_OFF_PRESSURE = 0.1e-10  # "0.1E-10 UUU"  = HV off


class GammaVacuumSPCe(Device, metaclass=DeviceMeta):
    """
    Device server for the Gamma Vacuum DIGITEL SPCe ion pump power supply.
    Connects via the Ethernet Telnet interface (default TCP port 23).
    """

    # -----------------
    # Device Properties
    # -----------------

    Host = device_property(
        dtype='str',
        doc='IP address or hostname of the SPCe controller',
    )

    Port = device_property(
        dtype='int',
        default_value=23,
        doc='TCP port for the Telnet interface (default 23)',
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

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        self._sock = None
        self._connect()

    def delete_device(self):
        self._disconnect()

    def always_executed_hook(self):
        pass

    # ------------------
    # Connection helpers
    # ------------------

    def _connect(self):
        """Open the TCP/Telnet connection and set initial device state."""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(5.0)
            self._sock.connect((self.Host, self.Port))
            # Discard any Telnet negotiation bytes or welcome banner
            self._sock.settimeout(1.0)
            try:
                self._sock.recv(1024)
            except socket.timeout:
                pass
            self._sock.settimeout(5.0)
            # Query HV state to set the Tango state
            resp = self._send_command('61')
            parts = resp.split()
            if len(parts) >= 4 and parts[3] == 'YES':
                self.set_state(DevState.ON)
            else:
                self.set_state(DevState.OFF)
            self.set_status("Connected to SPCe at %s:%d" % (self.Host, self.Port))
        except Exception as e:
            self._sock = None
            self.set_state(DevState.FAULT)
            self.set_status("Connection failed: %s" % str(e))

    def _disconnect(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _send_command(self, cmd, data=None):
        """
        Send a Telnet-format SPCe command and return the response string.

        Command format:  spc <cmd> [data]\\r\\n
        Response format: <ADDR> <OK|ER> <CODE> [fields...] <CHECKSUM>\\r
        """
        if self._sock is None:
            self._connect()
        if data is not None:
            msg = ("spc %s %s\r\n" % (cmd, data)).encode('ascii')
        else:
            msg = ("spc %s\r\n" % cmd).encode('ascii')
        try:
            self._sock.sendall(msg)
            response = b""
            while True:
                c = self._sock.recv(1)
                if not c:
                    break
                # Strip Telnet IAC bytes (0xFF and following two bytes)
                if c == b'\xff':
                    self._sock.recv(2)
                    continue
                response += c
                if c in (b'\r', b'\n'):
                    # Consume the paired LF or CR if present
                    self._sock.settimeout(0.2)
                    try:
                        extra = self._sock.recv(1)
                        if extra not in (b'\r', b'\n'):
                            # Not a line-ending pair — put it back by re-reading
                            pass
                    except socket.timeout:
                        pass
                    self._sock.settimeout(5.0)
                    break
            return response.decode('ascii').strip()
        except Exception as e:
            self._disconnect()
            raise PyTango.DevFailed("Communication error: %s" % str(e))

    # ------------------
    # Attributes methods
    # ------------------

    def read_Pressure(self):
        # Response: "<ADDR> OK 0B <value> <unit> <checksum>"
        # HV off sentinel: 0.1E-10 (any unit)
        resp = self._send_command('0b')
        parts = resp.split()
        if len(parts) < 5 or parts[1] != 'OK':
            raise PyTango.DevFailed("Unexpected pressure response: %s" % resp)
        value = float(parts[3])
        unit = parts[4]
        factor = _UNIT_TO_MBAR.get(unit, 1.0)
        return value * factor

    def read_Current(self):
        # Response: "<ADDR> OK 0A <value> AMPS <checksum>"
        # HV off sentinel: 0.1E-09 AMPS
        resp = self._send_command('0a')
        parts = resp.split()
        if len(parts) < 4 or parts[1] != 'OK':
            raise PyTango.DevFailed("Unexpected current response: %s" % resp)
        return float(parts[3])

    def read_Voltage(self):
        # Response: "<ADDR> OK 0C <value> <checksum>"
        resp = self._send_command('0c')
        parts = resp.split()
        if len(parts) < 4 or parts[1] != 'OK':
            raise PyTango.DevFailed("Unexpected voltage response: %s" % resp)
        return float(parts[3])

    def read_SupplyStatus(self):
        # Response: "<ADDR> OK 0D <message words...> <checksum>"
        # The status message occupies all fields between index 3 and the last.
        resp = self._send_command('0d')
        parts = resp.split()
        if len(parts) < 4 or parts[1] != 'OK':
            return resp
        return ' '.join(parts[3:-1])

    # --------
    # Commands
    # --------

    @command()
    @DebugIt()
    def On(self):
        """Enable high voltage (start ion pump)."""
        self._send_command('37')
        self.set_state(DevState.ON)

    @command()
    @DebugIt()
    def Off(self):
        """Disable high voltage (stop ion pump)."""
        self._send_command('38')
        self.set_state(DevState.OFF)

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
        return self._send_command(cmd, data)


# ----------
# Run server
# ----------

def main(args=None, **kwargs):
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((GammaVacuumSPCe,), args=args, **kwargs)

if __name__ == '__main__':
    main()
