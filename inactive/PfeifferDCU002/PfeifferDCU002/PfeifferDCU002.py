# -*- coding: utf-8 -*-
#
# This file is part of the PfeifferDCU002 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" PfeifferDCU002

This is a server that provides the same funcionality as the Pfeiffer DCU display unit.
"""

# PyTango imports
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device, DeviceMeta
from tango.server import command
from tango.server import device_property
from tango import AttrQuality, DispLevel, DevState
from tango import AttrWriteType, PipeWriteType
# Additional import
# PROTECTED REGION ID(PfeifferDCU002.additionnal_import) ENABLED START #
import os
import sys
import serial
# PROTECTED REGION END #    //  PfeifferDCU002.additionnal_import

__all__ = ["PfeifferDCU002", "main"]


class PfeifferDCU002(Device, metaclass=DeviceMeta):
    """
    This is a server that provides the same funcionality as the Pfeiffer DCU display unit.
    """
    # PROTECTED REGION ID(PfeifferDCU002.class_variable) ENABLED START #

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

    # PROTECTED REGION END #    //  PfeifferDCU002.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(PfeifferDCU002.init_device) ENABLED START #
        self.ser=serial.Serial(self.SerialPort,9600,bytesize=8,parity="N",stopbits=1)
        # PROTECTED REGION END #    //  PfeifferDCU002.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(PfeifferDCU002.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  PfeifferDCU002.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(PfeifferDCU002.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  PfeifferDCU002.delete_device


    # --------
    # Commands
    # --------

    @command(
    dtype_in='str', 
    dtype_out='str', 
    )
    @DebugIt()
    def readParameter(self, argin):
        # PROTECTED REGION ID(PfeifferDCU002.readParameter) ENABLED START #
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","00",argin[0:3],"=?")
        return rdata
        # PROTECTED REGION END #    //  PfeifferDCU002.readParameter

    @command(
    dtype_in=('str',), 
    dtype_out='str', 
    )
    @DebugIt()
    def setParameter(self, argin):
        # PROTECTED REGION ID(PfeifferDCU002.setParameter) ENABLED START #
        parameter=argin[0]
        data=argin[1]
        parameter=parameter[0:3]
        (radd,raction,rparameter,rdata,rcrc)=self.sendcommand("001","10",parameter,data)
        return rdata
        # PROTECTED REGION END #    //  PfeifferDCU002.setParameter

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(PfeifferDCU002.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((PfeifferDCU002,), args=args, **kwargs)
    # PROTECTED REGION END #    //  PfeifferDCU002.main

if __name__ == '__main__':
    main()
