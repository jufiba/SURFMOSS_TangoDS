# -*- coding: utf-8 -*-
#
# This file is part of the LeyboldIG3 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" LeyboldIG3

Server to use remotely the Leybold IG3 Gauge Electronics.
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
# PROTECTED REGION ID(LeyboldIG3.additionnal_import) ENABLED START #
import os
import sys
import time
import serial

class IG3Error(Exception):
    """The IG3 did not answer, or answered something that is not a frame.

    One exception for the three ways the exchange can fail — no reply, a reply
    that does not check out, and a reply whose type is not in the protocol —
    because to every caller they mean the same thing: there is no reading to be
    had. response() used to return None for the third and raise IndexError for
    the first two, and every caller then subscripted it.
    """


# PROTECTED REGION END #    //  LeyboldIG3.additionnal_import

__all__ = ["LeyboldIG3", "main"]


class LeyboldIG3(Device):
    """
    Server to use remotely the Leybold IG3 Gauge Electronics.
    """
    # PROTECTED REGION ID(LeyboldIG3.class_variable) ENABLED START #
    def cmd(self,a):
        b=bytes(a,"ascii")
        self.ser.write(bytes([2,len(b)])+b+bytes([sum(b)%256]))
    def response(self):
        """Read one reply frame. ("ACK"|"NAK", payload), or IG3Error.

        Every read is checked for length before anything is indexed. A read
        that times out returns short rather than raising, so h[1] on an empty
        header was an IndexError -- and that is the likely failure, not the
        exotic one: it is what a disconnected or silent gauge produces.
        """
        h=self.ser.read(2)
        if (len(h)<2):
            raise IG3Error("no reply: %d of the 2 header bytes arrived "
                           "(timeout, cable, or wrong baud rate)"%len(h))
        if (h[1]==0):
            raise IG3Error("the header announces an empty body")
        d=self.ser.read(h[1])
        if (len(d)<h[1]):
            raise IG3Error("truncated reply: %d of the %d bytes announced"
                           %(len(d),h[1]))
        raw=self.ser.read(1)
        if (len(raw)<1):
            raise IG3Error("the checksum byte never arrived")
        ck=int.from_bytes(raw,byteorder="big")
        if (sum(d)%256!=ck):
            raise IG3Error("checksum mismatch: computed %d, received %d"
                           %(sum(d)%256,ck))
        if (d[0]==0x06):
            return("ACK",d[1:])
        if (d[0]==0x15):
            return("NAK",d[1:])
        raise IG3Error("unrecognised frame, first byte 0x%02x"%d[0])
    # PROTECTED REGION END #    //  LeyboldIG3.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str', default_value="/dev/ttyUSB0"
    )

    Speed = device_property(
        dtype='uint16', default_value=9600
    )

    # ----------
    # Attributes
    # ----------

    Pressure = attribute(
        dtype='double',
        label="Pressure",
        unit="mbar",
        format="%.1e",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(LeyboldIG3.init_device) ENABLED START #
        # An exception escaping init_device makes PyTango exit the whole
        # server, and the Starter then leaves it for dead. Everything that can
        # fail is caught here and turned into FAULT with the reason in the
        # status, so the device stays up and says what is wrong.
        #
        # The old code caught serial.SerialTimeoutException, which pyserial
        # raises on a write that times out. Nothing here writes with a timeout;
        # a read that times out returns short and used to become an IndexError
        # inside response(). It is IG3Error that matters now.
        try:
            self.ser=serial.Serial(self.SerialPort,baudrate=self.Speed,timeout=1.0)
        except serial.SerialException as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't open %s: %s"%(self.SerialPort,e))
            self.error_stream("Can't open %s: %s"%(self.SerialPort,e))
            return
        try:
            self.cmd("H")
            (kind,payload)=self.response()
            if (kind=="NAK"):
                self.set_state(tango.DevState.FAULT)
                self.set_status("IG3 is saying it does not understand me")
                self.debug_stream("IG3 is saying it does not understand me")
                return
            if (str(payload[0:3],"ascii")!="IG3"):
                self.set_state(tango.DevState.FAULT)
                self.set_status("This is not an IG3, it identifies as %s"
                                %str(payload,"ascii"))
                self.debug_stream("This is not an IG3")
                return
            self.set_status("Connected to Leybold IG3")
            self.debug_stream("Connected to Leybold IG3")
            self.cmd("S14")
            (kind,payload)=self.response()
            if (str(payload,"ascii")=="1"):
                self.set_state(tango.DevState.ON)
            else:
                self.set_state(tango.DevState.OFF)
        except IG3Error as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't talk to the IG3: %s"%e)
            self.error_stream("Can't talk to the IG3: %s"%e)
        # PROTECTED REGION END #    //  LeyboldIG3.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(LeyboldIG3.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  LeyboldIG3.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(LeyboldIG3.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  LeyboldIG3.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Pressure(self):
        # PROTECTED REGION ID(LeyboldIG3.Pressure_read) ENABLED START #
        # 0.0 on a pressure gauge reads as perfect vacuum, which is the most
        # dangerous value this attribute can hand to an interlock or an alarm:
        # it says the chamber is fine at exactly the moment nothing is known.
        # Every path that has no reading returns INVALID instead, so a client
        # that checks quality sees nothing rather than good news, and one that
        # does not at least gets a number that cannot be mistaken for a good
        # one. Same reasoning as SEAWaterflowmeter and TempSensorDS18B20.
        state=self.get_state()
        if (state==tango.DevState.OFF):
            return (0.0,time.time(),tango.AttrQuality.ATTR_INVALID)
        self.cmd("S00")
        try:
            (kind,payload)=self.response()
        except IG3Error as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't read the pressure: %s"%e)
            self.error_stream("Can't read the pressure: %s"%e)
            return (0.0,time.time(),tango.AttrQuality.ATTR_INVALID)
        if (kind=="ACK"):
            return float(payload)
        # Only NAK reaches here; a bad frame or no frame raised above. The old
        # code did r[0]+r[1], concatenating str with bytes, so the error path
        # raised TypeError while reporting the error.
        self.set_state(tango.DevState.FAULT)
        self.set_status("IG3 refused the pressure request: %s"
                        %str(payload,"ascii"))
        self.debug_stream("IG3 refused the pressure request")
        return (0.0,time.time(),tango.AttrQuality.ATTR_INVALID)
        # PROTECTED REGION END #    //  LeyboldIG3.Pressure_read


    # --------
    # Commands
    # --------

    @command(
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def Start(self):
        # PROTECTED REGION ID(LeyboldIG3.Start) ENABLED START #
        state=self.get_state()
        if (state==tango.DevState.ON):
            return
        elif (state==tango.DevState.OFF):
            self.cmd("R09")
            try:
                (kind,payload)=self.response()
            except IG3Error as e:
                self.set_state(tango.DevState.FAULT)
                self.set_status("Can't talk to the IG3: %s"%e)
                self.error_stream("Can't talk to the IG3: %s"%e)
                return
            if (kind=="ACK"):
                self.set_state(tango.DevState.ON)
            else:
                self.set_status("IG3 refused: %s"%str(payload,"ascii"))
                self.debug_stream("IG3 refused: %s"%str(payload,"ascii"))
                self.set_state(tango.DevState.FAULT)
        # PROTECTED REGION END #    //  LeyboldIG3.Start

    @command(
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(LeyboldIG3.Stop) ENABLED START #
        state=self.get_state()
        if (state==tango.DevState.OFF):
            return
        else:
            self.cmd("R10")
            try:
                (kind,payload)=self.response()
            except IG3Error as e:
                self.set_state(tango.DevState.FAULT)
                self.set_status("Can't talk to the IG3: %s"%e)
                self.error_stream("Can't talk to the IG3: %s"%e)
                return
            if (kind=="ACK"):
                self.set_state(tango.DevState.OFF)
            else:
                self.set_status("IG3 refused: %s"%str(payload,"ascii"))
                self.debug_stream("IG3 refused: %s"%str(payload,"ascii"))
                self.set_state(tango.DevState.FAULT)
        # PROTECTED REGION END #    //  LeyboldIG3.Stop

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def SendCommand(self, argin):
        # PROTECTED REGION ID(LeyboldIG3.SendCommand) ENABLED START #
        # Deliberately not caught: this is the expert diagnostic command, and a
        # DevFailed carrying the real reason is more use at the Jive prompt
        # than a string that hides it.
        self.cmd(argin)
        (kind,payload)=self.response()
        return kind+" "+str(payload,"ascii")
        # PROTECTED REGION END #    //  LeyboldIG3.SendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(LeyboldIG3.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((LeyboldIG3,), args=args, **kwargs)
    # PROTECTED REGION END #    //  LeyboldIG3.main

if __name__ == '__main__':
    main()
