# -*- coding: utf-8 -*-
#
# This file is part of the PfeifferHiscroll project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" PfeifferHiscroll

This is a server that provides the same funcionality as the Pfeiffer DCU display unit.
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
# PROTECTED REGION ID(PfeifferHiscroll.additionnal_import) ENABLED START #
import os
import sys
import serial

class PfeifferError(Exception):
    """The pump did not answer, or answered something that is not a frame.

    One exception for every way the exchange can fail -- no reply, a truncated
    one, a length that does not match, a bad checksum -- because to every caller
    they mean the same thing: there is no reading to be had.
    """


# PROTECTED REGION END #    //  PfeifferHiscroll.additionnal_import

__all__ = ["PfeifferHiscroll", "main"]


class PfeifferHiscroll(Device):
    """
    This is a server that provides the same funcionality as the Pfeiffer DCU display unit.
    """
    # PROTECTED REGION ID(PfeifferHiscroll.class_variable) ENABLED START #
    # A frame is address(3) action(2) parameter(3) length(2) data(length)
    # checksum(3) CR, so the shortest one that can arrive is 14 characters.
    MINFRAME=14

    def sendcommand(self,address,action,parameter,data):
        """Send one frame and return (address,action,parameter,data,checksum).

        Raises PfeifferError if no usable reply came back.

        read_until() takes the terminator positionally. It was being passed as
        terminator=, the pyserial 2.x name that 3.x renamed to `expected`, so
        every exchange raised TypeError -- and from init_device that exits the
        whole server. Positional works on both versions.

        The reply is then checked before anything is indexed. A read that times
        out comes back short rather than raising, so int(resp[8:10]) on '' was a
        ValueError and rdata[0] an IndexError -- and that is the likely failure,
        not the exotic one: it is what a silent or unplugged pump produces.
        """
        cmd_string=address+action+parameter+"%02d"%len(data)+data
        cmd=(cmd_string+"%03d"%self.crc_code(cmd_string)+"\r").encode("ascii")
        # Anything still in the buffer is the tail of an exchange that did not
        # check out. Left there, it would be read as the reply to this command,
        # and init_device sends two in a row.
        self.ser.reset_input_buffer()
        self.ser.write(cmd)
        resp=self.ser.read_until(b"\r").decode("ascii")
        where="%s%s"%(action,parameter)
        if (not resp.endswith("\r")):
            raise PfeifferError("no reply to %s: %d characters arrived without a "
                                "terminator (timeout, cable, or wrong baud rate)"
                                %(where,len(resp)))
        if (len(resp)<self.MINFRAME):
            raise PfeifferError("short reply to %s: %d characters, %d is the "
                                "shortest frame"%(where,len(resp),self.MINFRAME))
        if (not resp[8:10].isdigit()):
            raise PfeifferError("reply to %s announces no length: %r"
                                %(where,resp[8:10]))
        n=int(resp[8:10])
        if (len(resp)!=n+self.MINFRAME):
            raise PfeifferError("reply to %s announces %d data characters but "
                                "carries %d"%(where,n,len(resp)-self.MINFRAME))
        # The checksum covers everything ahead of it: the 10 header characters
        # and the n of data, which is all of the frame but the checksum and CR.
        body=resp[:-4]
        rcrc=resp[-4:-1]
        if (rcrc!="%03d"%self.crc_code(body)):
            raise PfeifferError("checksum mismatch on the reply to %s: computed "
                                "%03d, received %s"%(where,self.crc_code(body),rcrc))
        if (resp[5:8]!=parameter):
            raise PfeifferError("asked for parameter %s and the reply is for %s "
                                "(the exchange is out of step)"%(parameter,resp[5:8]))
        return(resp[0:3],resp[3:5],resp[5:8],resp[10:10+n],rcrc)

    def crc_code(self,a):
        result=0
        for i in range(0,len(a)):
            result = result + ord(a[i])
        result%=256
        return(result)
    # PROTECTED REGION END #    //  PfeifferHiscroll.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str',
    )

    # ----------
    # Attributes
    # ----------

    Power = attribute(
        dtype='int16',
        unit="W",
    )

    TemperatureElectronics = attribute(
        dtype='int16',
        unit="°C",
    )

    ActualSpeed = attribute(
        dtype='uint16',
        unit="rpm",
    )

    TemperatureMotor = attribute(
        dtype='uint16',
        unit="°C",
    )

    Current = attribute(
        dtype='double',
        unit="A",
    )

    TemperatureFinalStage = attribute(
        dtype='double',
        unit="°C",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(PfeifferHiscroll.init_device) ENABLED START #
        self.ser=None
        # An exception escaping init_device makes PyTango exit the whole
        # server, and the Starter then leaves it for dead -- that is what a
        # stale SerialPort property and a pump that never answers both used to
        # do. Everything that can fail is caught here and turned into FAULT
        # with the reason in the status, so the device stays up and says what
        # is wrong.
        try:
            self.ser=serial.Serial(self.SerialPort,9600,bytesize=8,parity="N",stopbits=1,timeout=1)
        except serial.SerialException as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't open %s: %s"%(self.SerialPort,e))
            self.error_stream("Can't open %s: %s"%(self.SerialPort,e))
            return
        try:
            self.sendcommand("002","10","060","2")
            (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("002","00","010","=?")
        except PfeifferError as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("No usable answer on %s: %s"%(self.SerialPort,e))
            self.error_stream("No usable answer on %s: %s"%(self.SerialPort,e))
            return
        # A reply can carry an empty data field, and rdata[0] on it was an
        # IndexError.
        if (rdata.startswith("1")):
            self.set_state(tango.DevState.ON)
        else:
            self.set_state(tango.DevState.OFF)
        # PROTECTED REGION END #    //  PfeifferHiscroll.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(PfeifferHiscroll.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  PfeifferHiscroll.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(PfeifferHiscroll.delete_device) ENABLED START #
        if (self.ser is not None):
            self.ser.close()
        # PROTECTED REGION END #    //  PfeifferHiscroll.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Power(self):
        # PROTECTED REGION ID(PfeifferHiscroll.Power_read) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("002","00","316","=?")
        return int(rdata)
        # PROTECTED REGION END #    //  PfeifferHiscroll.Power_read

    def read_TemperatureElectronics(self):
        # PROTECTED REGION ID(PfeifferHiscroll.TemperatureElectronics_read) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("002","00","326","=?")
        return int(rdata)
        # PROTECTED REGION END #    //  PfeifferHiscroll.TemperatureElectronics_read

    def read_ActualSpeed(self):
        # PROTECTED REGION ID(PfeifferHiscroll.ActualSpeed_read) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("002","00","398","=?")
        return int(rdata)
        # PROTECTED REGION END #    //  PfeifferHiscroll.ActualSpeed_read

    def read_TemperatureMotor(self):
        # PROTECTED REGION ID(PfeifferHiscroll.TemperatureMotor_read) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("002","00","346","=?")
        return int(rdata)
        # PROTECTED REGION END #    //  PfeifferHiscroll.TemperatureMotor_read

    def read_Current(self):
        # PROTECTED REGION ID(PfeifferHiscroll.Current_read) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("002","00","310","=?")
        return int(rdata)/100.0
        # PROTECTED REGION END #    //  PfeifferHiscroll.Current_read

    def read_TemperatureFinalStage(self):
        # PROTECTED REGION ID(PfeifferHiscroll.TemperatureFinalStage_read) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("002","00","316","=?")
        return int(rdata)
        # PROTECTED REGION END #    //  PfeifferHiscroll.TemperatureFinalStage_read


    # --------
    # Commands
    # --------

    @command(
    dtype_in='str', 
    dtype_out='str', 
    )
    @DebugIt()
    def readParameter(self, argin):
        # PROTECTED REGION ID(PfeifferHiscroll.readParameter) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("002","00",argin[0:3],"=?")
        return rdata
        # PROTECTED REGION END #    //  PfeifferHiscroll.readParameter

    @command(
    dtype_in=('str',), 
    dtype_out='str', 
    )
    @DebugIt()
    def setParameter(self, argin):
        # PROTECTED REGION ID(PfeifferHiscroll.setParameter) ENABLED START #
        parameter=argin[0]
        data=argin[1]
        parameter=parameter[0:3]
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("002","10",parameter,data)
        return rdata
        # PROTECTED REGION END #    //  PfeifferHiscroll.setParameter

    @command(
    )
    @DebugIt()
    def Start(self):
        # PROTECTED REGION ID(PfeifferHiscroll.Start) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("002","10","010","111111")
        if (rdata=="111111"):
            self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  PfeifferHiscroll.Start

    @command(
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(PfeifferHiscroll.Stop) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("002","10","010","000000")
        if (rdata=="000000"):
            self.set_state(tango.DevState.OFF)
        # PROTECTED REGION END #    //  PfeifferHiscroll.Stop

    @command(
    )
    @DebugIt()
    def Standby(self):
        # PROTECTED REGION ID(PfeifferHiscroll.Standby) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("002","10","002","111111")
        if (rdata=="111111"):
            self.set_state(tango.DevState.STANDBY)
        # PROTECTED REGION END #    //  PfeifferHiscroll.Standby

    @command(
    )
    @DebugIt()
    def Normal(self):
        # PROTECTED REGION ID(PfeifferHiscroll.Normal) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("002","10","002","000000")
        if (rdata=="000000"):
            self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  PfeifferHiscroll.Normal

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(PfeifferHiscroll.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((PfeifferHiscroll,), args=args, **kwargs)
    # PROTECTED REGION END #    //  PfeifferHiscroll.main

if __name__ == '__main__':
    main()
