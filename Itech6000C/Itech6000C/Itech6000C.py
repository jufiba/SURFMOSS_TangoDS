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
from tango.server import Device, DeviceMeta
from tango.server import attribute, command
from tango.server import device_property
from tango import AttrQuality, DispLevel, DevState
from tango import AttrWriteType, PipeWriteType
# Additional import
# PROTECTED REGION ID(Itech6000C.additionnal_import) ENABLED START #
import os
import sys
import socket

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False
    
# PROTECTED REGION END #    //  Itech6000C.additionnal_import

__all__ = ["Itech6000C", "main"]


class Itech6000C(Device, metaclass=DeviceMeta):
    """
    ITech6000C control through ethernet socket.
    """
    # PROTECTED REGION ID(Itech6000C.class_variable) ENABLED START #
    ItechConnected = False

    def TCPBlockingReceive(self):
        Bytereceived = b'0'
        szData = ''
        szData=self.s.recv(1024).decode("ascii")
        return szData
        while ord(Bytereceived) != 0:
            ReceivedLength = 0
            while ReceivedLength == 0:
                Bytereceived = self.s.recv(1)
                #print 'Bytereceived=',Bytereceived,'ord(Bytereceived)=',ord(Bytereceived)
                ReceivedLength = len(Bytereceived)
            if ord(Bytereceived) != 0:
                szData = szData + Bytereceived
            print(szData,"test")
        return szData

    def connect(self):
        if self.ItechConnected:
            return
        else:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self.s.connect((self.IP, self.Port))
            except:
                self.ItechConnected = False
                self.set_state(tango.DevState.FAULT)
                self.set_status("Can't connect to Itech6000C")
                self.debug_stream("Can't connect to Itech6000C")
                return
            self.ItechConnected = True
            self.set_status("Connected to Itech6000C")
            self.debug_stream("Connected to Itech6000C")

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

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(Itech6000C.init_device) ENABLED START #
        self.connect()
        self.s.send(b"OUTPUT?\n")
        data = self.TCPBlockingReceive()
        print(data)
        if (data[0]=="1"):
            self.set_state(tango.DevState.ON)
        else:
            self.set_state(tango.DevState.OFF)
        # PROTECTED REGION END #    //  Itech6000C.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(Itech6000C.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  Itech6000C.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(Itech6000C.delete_device) ENABLED START #
        self.disconnect()
        # PROTECTED REGION END #    //  Itech6000C.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Current(self):
        # PROTECTED REGION ID(Itech6000C.Current_read) ENABLED START #
        self.s.send(b"MEASure:SCALar:CURRent:DC?\n")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  Itech6000C.Current_read

    def read_Voltage(self):
        # PROTECTED REGION ID(Itech6000C.Voltage_read) ENABLED START #
        self.s.send(b"MEASure:SCALar:VOLTAGE:DC?\n")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  Itech6000C.Voltage_read

    def read_Power(self):
        # PROTECTED REGION ID(Itech6000C.Power_read) ENABLED START #
        self.s.send(b"MEASure:SCALar:POWER:DC?\n")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  Itech6000C.Power_read

    def read_SetVoltage(self):
        # PROTECTED REGION ID(Itech6000C.SetVoltage_read) ENABLED START #
        self.s.send(b"SOURce:VOLTAGE:LEVel:IMMediate:AMPLitude?\n")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  Itech6000C.SetVoltage_read

    def write_SetVoltage(self, value):
        # PROTECTED REGION ID(Itech6000C.SetVoltage_write) ENABLED START #
        self.s.send(("SOURce:VOLTAGE:LEVel:IMMediate:AMPLitude %f\n"%(value)).encode("ascii"))
        # PROTECTED REGION END #    //  Itech6000C.SetVoltage_write

    def read_SetCurrent(self):
        # PROTECTED REGION ID(Itech6000C.SetCurrent_read) ENABLED START #
        self.s.send(b"SOURce:CURRENT:LEVel:IMMediate:AMPLitude?\n")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  Itech6000C.SetCurrent_read

    def write_SetCurrent(self, value):
        # PROTECTED REGION ID(Itech6000C.SetCurrent_write) ENABLED START #
        self.s.send(("SOURce:CURRENT:LEVel:IMMediate:AMPLitude %f\n"%(value)).encode("ascii"))
        # PROTECTED REGION END #    //  Itech6000C.SetCurrent_write

    def read_Identification(self):
        # PROTECTED REGION ID(Itech6000C.Identification_read) ENABLED START #
        self.s.send(b"SYST:VERS?\n")
        data = self.TCPBlockingReceive()
        return data
        # PROTECTED REGION END #    //  Itech6000C.Identification_read


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
        self.s.send((argin+"\n").encode("ascii"))
        return
        # PROTECTED REGION END #    //  Itech6000C.sendCommand

    @command(
    )
    @DebugIt()
    def OutputOn(self):
        # PROTECTED REGION ID(Itech6000C.OutputOn) ENABLED START #
        self.s.send(b"OUTPUT ON\n")
        self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  Itech6000C.OutputOn

    @command(
    )
    @DebugIt()
    def OutputOff(self):
        # PROTECTED REGION ID(Itech6000C.OutputOff) ENABLED START #
        self.s.send(b"OUTPUT OFF\n")
        self.set_state(tango.DevState.OFF)
        # PROTECTED REGION END #    //  Itech6000C.OutputOff

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def SendQuery(self, argin):
        # PROTECTED REGION ID(Itech6000C.SendQuery) ENABLED START #
        self.s.send((argin+"\n").encode("ascii"))
        data = self.TCPBlockingReceive()
        return data
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
