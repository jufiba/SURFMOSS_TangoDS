# -*- coding: utf-8 -*-
#
# This file is part of the NetworkUPSTool project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" NetworkUPSTool

A wrapper for showing the more relevant information from NUT, the network UPS
tool.

This is the server you want still talking when the mains is misbehaving, so it
is written not to depend on anything having gone right earlier:

  upsd not up at start-up   -> FAULT with the reason, and a retry every
                               RETRY_PERIOD seconds. It used to take the whole
                               server down: an exception escaping init_device
                               makes PyTango exit the process.
  upsd restarted underneath -> the session is re-established on the next read.
                               A single client is opened once by PyNUT and
                               never renewed, so a restart of upsd leaves this
                               end with a socket that answers BrokenPipeError
                               for ever. Found in exactly that state on
                               30-Aug-2026: state ON, four attributes failing,
                               the last real reading hours old.
  a variable the UPS does
  not publish               -> INVALID, not an exception. Plenty of models
                               report no temperature.
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
# PROTECTED REGION ID(NetworkUPSTool.additionnal_import) ENABLED START #
import os
import sys
import time
import PyNUT

# Seconds between attempts to reach upsd again while the server sits in FAULT.
RETRY_PERIOD = 10

# One fetch of the fifty-odd variables serves a whole sweep of the four
# attributes. Each one used to ask upsd separately, so a single screenful cost
# four round trips for data that is refreshed every two seconds anyway.
CACHE_SECONDS = 0.5
# PROTECTED REGION END #    //  NetworkUPSTool.additionnal_import

__all__ = ["NetworkUPSTool", "main"]


class NetworkUPSTool(Device):
    """
    A wrapper for showing the more relevant information from NUT, the network UPS tool.
    """
    # PROTECTED REGION ID(NetworkUPSTool.class_variable) ENABLED START #
    # Decoding happens here, once, rather than at each of the five call sites:
    # python3-nut hands back bytes for both keys and values, while the code
    # below indexes with str literals and compares against str. The old
    # python-nut, on Python 2, made no distinction. class_variable is the only
    # region inside the class body that POGO preserves, so this is where a
    # helper method has to live.
    #
    # isinstance rather than a bare .decode() so the server does not care which
    # of the two packagings it is running against -- being tied to one is what
    # broke it in the first place.
    def _get_vars(self):
        raw = self.client.GetUPSVars(self.UPSunitName)
        return {self._text(k): self._text(v) for k, v in raw.items()}

    @staticmethod
    def _text(value):
        return value.decode() if isinstance(value, bytes) else value

    def _connect(self):
        """Open a session with upsd and read the UPS once. True if it worked.

        Never raises. Kept out of init_device for two reasons: an exception
        there makes PyTango exit the whole server, and init_device runs
        exactly once, so a upsd that was not up yet used to leave this FAULT
        for good even after it came back.

        PyNUT takes a timeout argument and then ignores it -- its __init__
        assigns a hard 5 s -- so every call here is bounded, but do not expect
        to be able to change by how much.
        """
        self.lastconnect = time.time()
        self.client = None
        try:
            self.client = PyNUT.PyNUTClient()
            self.varsUPS = self._get_vars()
            # A list of str, not bytes: decoded here rather than at whatever
            # eventually reads it. Nothing does today.
            self.commUPS = [self._text(c) for c
                            in self.client.GetUPSCommands(self.UPSunitName)]
        except Exception as exc:
            self.client = None
            self.varsUPS = {}
            self.set_state(tango.DevState.FAULT)
            self.set_status("Cannot reach upsd for %s: %s"
                            % (self.UPSunitName, exc))
            self.error_stream("Cannot reach upsd for %s: %s"
                              % (self.UPSunitName, exc))
            return False
        self.lastfetch = time.time()
        self._set_state()
        return True

    def _set_state(self):
        """State and status from ups.status, which is a set of flags.

        Not one word. "OL CHRG" is a healthy UPS recharging after a cut, and
        "OB LB" is one on battery and nearly empty. Comparing the whole string
        against "OL" reported both, and every other combination, as FAULT --
        so the server called itself broken exactly when the UPS had something
        to say. FAULT is for this server being unable to do its job; what the
        UPS reports is ALARM.
        """
        flags = set(self.varsUPS.get("ups.status", "").split())
        if "OB" in flags:
            state = tango.DevState.ALARM if "LB" in flags \
                else tango.DevState.STANDBY
        elif "OL" in flags:
            state = tango.DevState.ON
        else:
            state = tango.DevState.ALARM
        self.set_state(state)
        self.set_status("%s: ups.status = %s"
                        % (self.UPSunitName,
                           self.varsUPS.get("ups.status", "(not reported)")))

    def _vars(self):
        """The variables, at most CACHE_SECONDS old, or None if upsd is gone.

        A failed fetch drops the session and opens a new one straight away,
        rather than waiting for RETRY_PERIOD: upsd runs on this machine, so a
        refused connection costs microseconds, and the case worth recovering
        from quickly -- upsd restarted underneath us -- is cured by exactly
        one reconnection.
        """
        now = time.time()
        if self.client is not None and now - self.lastfetch < CACHE_SECONDS:
            return self.varsUPS
        if self.client is not None:
            try:
                self.varsUPS = self._get_vars()
                self.lastfetch = time.time()
                self._set_state()
                return self.varsUPS
            except Exception as exc:
                self.warn_stream("lost the session to upsd (%s); reconnecting"
                                 % exc)
        if not self._connect():
            return None
        return self.varsUPS

    def _number(self, key):
        """One numeric variable, or None if it cannot be had right now."""
        variables = self._vars()
        if variables is None or key not in variables:
            return None
        try:
            return float(variables[key])
        except ValueError:
            return None

    @staticmethod
    def _invalid(value=0.0):
        return (value, time.time(), tango.AttrQuality.ATTR_INVALID)
    # PROTECTED REGION END #    //  NetworkUPSTool.class_variable

    # -----------------
    # Device Properties
    # -----------------

    UPSunitName = device_property(
        dtype='str',
    )

    # ----------
    # Attributes
    # ----------

    UpsStatus = attribute(
        dtype='str',
    )

    Temperature = attribute(
        dtype='double',
        label="Temperature",
        unit="°C",
    )

    Load = attribute(
        dtype='double',
        label="Load",
        unit="%",
    )

    Charge = attribute(
        dtype='double',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(NetworkUPSTool.init_device) ENABLED START #
        self.client = None
        self.varsUPS = {}
        self.commUPS = []
        self.lastfetch = 0.0
        self.lastconnect = 0.0
        self._connect()
        # PROTECTED REGION END #    //  NetworkUPSTool.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(NetworkUPSTool.always_executed_hook) ENABLED START #
        # Where a server that started before upsd picks itself up without an
        # operator Init. Rate-limited: callers should not pay for a refused
        # connection on every single request.
        if (self.get_state() == tango.DevState.FAULT
                and time.time() - self.lastconnect > RETRY_PERIOD):
            self._connect()
        # PROTECTED REGION END #    //  NetworkUPSTool.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(NetworkUPSTool.delete_device) ENABLED START #
        # PyNUT logs out and closes the socket in its __del__, so letting go
        # of the reference is the whole of it.
        self.client = None
        # PROTECTED REGION END #    //  NetworkUPSTool.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_UpsStatus(self):
        # PROTECTED REGION ID(NetworkUPSTool.UpsStatus_read) ENABLED START #
        # "OnLine" and "OnBattery" are a contract, not cosmetics: the legacy
        # PANIC alarm LEEM_POWER tested UpsStatus == "OnBattery" and the LEEM
        # synoptic still shows this attribute. Anything else is handed on raw.
        variables = self._vars()
        if variables is None:
            return self._invalid("")
        flags = set(variables.get("ups.status", "").split())
        if "OB" in flags:
            return "OnBattery"
        if "OL" in flags:
            return "OnLine"
        return variables.get("ups.status", "") or self._invalid("")
        # PROTECTED REGION END #    //  NetworkUPSTool.UpsStatus_read

    def read_Temperature(self):
        # PROTECTED REGION ID(NetworkUPSTool.Temperature_read) ENABLED START #
        value = self._number("ups.temperature")
        # INVALID rather than an error: upsd may be unreachable, and not every
        # model publishes this at all.
        return self._invalid() if value is None else value
        # PROTECTED REGION END #    //  NetworkUPSTool.Temperature_read

    def read_Load(self):
        # PROTECTED REGION ID(NetworkUPSTool.Load_read) ENABLED START #
        value = self._number("ups.load")
        # INVALID rather than an error: upsd may be unreachable, and not every
        # model publishes this at all.
        return self._invalid() if value is None else value
        # PROTECTED REGION END #    //  NetworkUPSTool.Load_read

    def read_Charge(self):
        # PROTECTED REGION ID(NetworkUPSTool.Charge_read) ENABLED START #
        value = self._number("battery.charge")
        # INVALID rather than an error: upsd may be unreachable, and not every
        # model publishes this at all.
        return self._invalid() if value is None else value
        # PROTECTED REGION END #    //  NetworkUPSTool.Charge_read


    # --------
    # Commands
    # --------

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(NetworkUPSTool.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((NetworkUPSTool,), args=args, **kwargs)
    # PROTECTED REGION END #    //  NetworkUPSTool.main

if __name__ == '__main__':
    main()
