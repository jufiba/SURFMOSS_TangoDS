# -*- coding: utf-8 -*-
#
# This file is part of the PfeifferTU400 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" PfeifferTU400

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
# PROTECTED REGION ID(PfeifferTU400.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  PfeifferTU400.additionnal_import

__all__ = ["PfeifferTU400", "main"]


class PfeifferTU400(Device):
    """
    This is a server that provides the same funcionality as the Pfeiffer DCU display unit.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(PfeifferTU400.class_variable) ENABLED START #
    
    def sendcommand(self,address,action,parameter,data):
    	cmd_string=address+action+parameter+"%02d"%len(data)+data
    	cmd=cmd_string+"%03d"%self.crc_code(cmd_string)+"\r"
    	self.ser.write(cmd)
    	resp=self.ser.read_until(terminator="\r")
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

    # PROTECTED REGION END #    //  PfeifferTU400.class_variable

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

    TemperatureBearing = attribute(
        dtype='int16',
        unit="ºC",
    )

    ActualSpeed = attribute(
        dtype='uint16',
        unit="rpm",
    )

    TemperatureMotor = attribute(
        dtype='uint16',
        unit="ºC",
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
        # PROTECTED REGION ID(PfeifferTU400.init_device) ENABLED START #
        self.ser=serial.Serial(self.SerialPort,9600,bytesize=8,parity="N",stopbits=1)
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","10","060","2")
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","00","010","=?")
        if (rdata[0]=="1"):
            self.set_state(PyTango.DevState.ON)
        else:
            self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  PfeifferTU400.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(PfeifferTU400.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  PfeifferTU400.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(PfeifferTU400.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  PfeifferTU400.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Power(self):
        # PROTECTED REGION ID(PfeifferTU400.Power_read) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","00","316","=?")
        return int(rdata)
        # PROTECTED REGION END #    //  PfeifferTU400.Power_read

    def read_TemperatureBearing(self):
        # PROTECTED REGION ID(PfeifferTU400.TemperatureBearing_read) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","00","342","=?")
        return int(rdata)
        # PROTECTED REGION END #    //  PfeifferTU400.TemperatureBearing_read

    def read_ActualSpeed(self):
        # PROTECTED REGION ID(PfeifferTU400.ActualSpeed_read) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","00","398","=?")
        return int(rdata)
        # PROTECTED REGION END #    //  PfeifferTU400.ActualSpeed_read

    def read_TemperatureMotor(self):
        # PROTECTED REGION ID(PfeifferTU400.TemperatureMotor_read) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","00","346","=?")
        return int(rdata)
        # PROTECTED REGION END #    //  PfeifferTU400.TemperatureMotor_read

    def read_Current(self):
        # PROTECTED REGION ID(PfeifferTU400.Current_read) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","00","310","=?")
        return int(rdata)/100.0
        # PROTECTED REGION END #    //  PfeifferTU400.Current_read


    # --------
    # Commands
    # --------

    @command(
    dtype_in='str', 
    dtype_out='str', 
    )
    @DebugIt()
    def readParameter(self, argin):
        # PROTECTED REGION ID(PfeifferTU400.readParameter) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","00",argin[0:3],"=?")
        return rdata
        # PROTECTED REGION END #    //  PfeifferTU400.readParameter

    @command(
    dtype_in=('str',), 
    dtype_out='str', 
    )
    @DebugIt()
    def setParameter(self, argin):
        # PROTECTED REGION ID(PfeifferTU400.setParameter) ENABLED START #
        parameter=argin[0]
        data=argin[1]
        parameter=parameter[0:3]
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","10",parameter,data)
        return rdata
        # PROTECTED REGION END #    //  PfeifferTU400.setParameter

    @command(
    )
    @DebugIt()
    def Start(self):
        # PROTECTED REGION ID(PfeifferTU400.Start) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","10","010","111111")
        if (rdata=="111111"):
            self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  PfeifferTU400.Start

    @command(
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(PfeifferTU400.Stop) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","10","010","000000")
        if (rdata=="000000"):
            self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  PfeifferTU400.Stop

    @command(
    )
    @DebugIt()
    def Standby(self):
        # PROTECTED REGION ID(PfeifferTU400.Standby) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","10","002","111111")
        if (rdata=="111111"):
            self.set_state(PyTango.DevState.STANDBY)
        # PROTECTED REGION END #    //  PfeifferTU400.Standby

    @command(
    )
    @DebugIt()
    def Normal(self):
        # PROTECTED REGION ID(PfeifferTU400.Normal) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","10","002","000000")
        if (rdata=="000000"):
            self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  PfeifferTU400.Normal

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(PfeifferTU400.main) ENABLED START #
    return run((PfeifferTU400,), args=args, **kwargs)
    # PROTECTED REGION END #    //  PfeifferTU400.main

if __name__ == '__main__':
    main()
