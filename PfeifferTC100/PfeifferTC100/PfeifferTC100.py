# -*- coding: utf-8 -*-
#
# This file is part of the PfeifferTC100 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" PfeifferTC100

This is a server that provides the same funcionality as the Pfeiffer DCU display unit.
"""

# PyTango imports
import PyTango
from PyTango import DebugIt
from PyTango.server import run
from PyTango.server import Device, DeviceMeta
from PyTango.server import attribute, command
from PyTango.server import device_property
from PyTango import AttrQuality, DispLevel, DevState
from PyTango import AttrWriteType, PipeWriteType
# Additional import
# PROTECTED REGION ID(PfeifferTC100.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  PfeifferTC100.additionnal_import

__all__ = ["PfeifferTC100", "main"]


class PfeifferTC100(Device, metaclass=DeviceMeta):
    """
    This is a server that provides the same funcionality as the Pfeiffer DCU display unit.
    """
    # PROTECTED REGION ID(PfeifferTC100.class_variable) ENABLED START #

    def sendcommand(self,address,action,parameter,data):
        cmd_string=address+action+parameter+"%02d"%len(data)+data
        cmd=(cmd_string+"%03d"%self.crc_code(cmd_string)+"\r").encode("ascii")
        self.ser.write(cmd)
        resp=self.ser.read_until(terminator=b"\r").decode("ascii")
        raddress=resp[0:3]
        raction=resp[3:5]
        rparameter=resp[5:8]
        rdata=resp[10:10+int(resp[8:10])]
        rcrc=resp[-4:-1]
        return(raddress,raction,rparameter,rdata,rcrc)

    def crc_code(self,a):
        result=0
        for i in range(0,len(a)):
            result = result + ord(a[i])
        result%=256
        return(result)

    # PROTECTED REGION END #    //  PfeifferTC100.class_variable

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

    ActualSpeed = attribute(
        dtype='uint16',
        unit="Hz",
    )

    Current = attribute(
        dtype='double',
        unit="A",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(PfeifferTC100.init_device) ENABLED START #
        self.ser=serial.Serial(self.SerialPort,9600,bytesize=8,parity="N",stopbits=1,timeout=1)
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","00","010","=?")
        if (rdata[0]=="1"):
            self.set_state(PyTango.DevState.ON)
        else:
            self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  PfeifferTC100.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(PfeifferTC100.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  PfeifferTC100.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(PfeifferTC100.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  PfeifferTC100.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Power(self):
        # PROTECTED REGION ID(PfeifferTC100.Power_read) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","00","316","=?")
        return int(rdata)
        # PROTECTED REGION END #    //  PfeifferTC100.Power_read

    def read_ActualSpeed(self):
        # PROTECTED REGION ID(PfeifferTC100.ActualSpeed_read) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","00","309","=?")
        return int(rdata)
        # PROTECTED REGION END #    //  PfeifferTC100.ActualSpeed_read

    def read_Current(self):
        # PROTECTED REGION ID(PfeifferTC100.Current_read) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","00","310","=?")
        return int(rdata)/100.0
        # PROTECTED REGION END #    //  PfeifferTC100.Current_read


    # --------
    # Commands
    # --------

    @command(
    dtype_in='str', 
    dtype_out='str', 
    )
    @DebugIt()
    def readParameter(self, argin):
        # PROTECTED REGION ID(PfeifferTC100.readParameter) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","00",argin[0:3],"=?")
        return rdata
        # PROTECTED REGION END #    //  PfeifferTC100.readParameter

    @command(
    dtype_in=('str',), 
    dtype_out='str', 
    )
    @DebugIt()
    def setParameter(self, argin):
        # PROTECTED REGION ID(PfeifferTC100.setParameter) ENABLED START #
        parameter=argin[0]
        data=argin[1]
        parameter=parameter[0:3]
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","10",parameter,data)
        return rdata
        # PROTECTED REGION END #    //  PfeifferTC100.setParameter

    @command(
    )
    @DebugIt()
    def Start(self):
        # PROTECTED REGION ID(PfeifferTC100.Start) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","10","010","111111")
        if (rdata=="111111"):
            self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  PfeifferTC100.Start

    @command(
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(PfeifferTC100.Stop) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","10","010","000000")
        if (rdata=="000000"):
            self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  PfeifferTC100.Stop

    @command(
    )
    @DebugIt()
    def Standby(self):
        # PROTECTED REGION ID(PfeifferTC100.Standby) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","10","002","111111")
        if (rdata=="111111"):
            self.set_state(PyTango.DevState.STANDBY)
        # PROTECTED REGION END #    //  PfeifferTC100.Standby

    @command(
    )
    @DebugIt()
    def Normal(self):
        # PROTECTED REGION ID(PfeifferTC100.Normal) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","10","002","000000")
        if (rdata=="000000"):
            self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  PfeifferTC100.Normal

    @command(
    dtype_in='uint16', 
    )
    @DebugIt()
    def SetRotSpeed(self, argin):
        # PROTECTED REGION ID(PfeifferTC100.SetRotSpeed) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","10","308","%06d"%argin)
        # PROTECTED REGION END #    //  PfeifferTC100.SetRotSpeed

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(PfeifferTC100.main) ENABLED START #
    return run((PfeifferTC100,), args=args, **kwargs)
    # PROTECTED REGION END #    //  PfeifferTC100.main

if __name__ == '__main__':
    main()
