# -*- coding: utf-8 -*-
#
# This file is part of the HuttingerPFGRF project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" HuttingerPFGRF

Driver for the Huttinger RF generators, such as the PFG-RF300 a power supply for magnetron sputtering growth.
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
# PROTECTED REGION ID(HuttingerPFGRF.additionnal_import) ENABLED START #
import serial
import struct
# PROTECTED REGION END #    //  HuttingerPFGRF.additionnal_import

__all__ = ["HuttingerPFGRF", "main"]


class HuttingerPFGRF(Device):
    """
    Driver for the Huttinger RF generators, such as the PFG-RF300 a power supply for magnetron sputtering growth.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(HuttingerPFGRF.class_variable) ENABLED START #
    
    def sendcommand(self,address,command,data):
        # Asume command is an string in hexadecimal, say C4
        # address is 0 for generator, 1 for matchbox
        cmd=struct.pack(">BBH",address,int(command,16),data)
        cmd_string=cmd+self.crc_code(cmd)
        try:
            self.ser.write(cmd_string)
        except:
            self.set_state(PyTango.DevState.FAULT)
        return(self.ser.read(5))
    
    def parse_response(self,resp):
        (address,cmd,data,crc)=struct.unpack(">BBHB",resp)
        cmd=ord(resp[1])
        if (cmd==21):
            command="NACK"
        elif (cmd==6):
            command="ACK"
        else:
            command="%x"%ord(resp[1])
        return(address,command,data)
                
    def byte_hex(self,a):
         return("%02x"%ord(a))
                
    def crc_code(self,a):
         result=0
         for i in range(0,len(a)):
            result = result ^ ord(a[i])
         return(struct.pack(">B",result))
    
    # PROTECTED REGION END #    //  HuttingerPFGRF.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str',
        mandatory=True
    )

    # ----------
    # Attributes
    # ----------

    NominalPower = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        label="Nominal Power",
        unit="W",
        standard_unit="W",
        display_unit="W",
        max_value=300,
        min_value=0,
    )

    NominalDCBias = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        label="Nominal DCBias",
        unit="V",
        standard_unit="V",
        display_unit="V",
        format="%d",
        max_value=1000,
        min_value=0,
    )

    Channel = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
    )

    RegulationMode = attribute(
        dtype='char',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        label="RegMode",
        max_value=4,
        min_value=1,
        doc="1=Power, 2=DCBias, 3=DeltaP, 4=RFPeak",
    )

    IncidentPower = attribute(
        dtype='double',
        label="Incident Power",
        unit="W",
        standard_unit="W",
        display_unit="W",
    )

    DCBias = attribute(
        dtype='double',
        label="DC Bias",
        unit="V",
        standard_unit="V",
        display_unit="V",
    )

    ReflectedPower = attribute(
        dtype='double',
        label="Reflected Power",
        unit="W",
        standard_unit="W",
        display_unit="W",
    )

    Limit = attribute(
        dtype='char',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        label="Limit",
        max_value=4,
        min_value=1,
        doc="1=Power, 2=DCBias, 3=DeltaP, 4=RFPeak",
    )

    NominalRFPeakVoltage = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
    )

    RFPeakVoltage = attribute(
        dtype='double',
    )

    Control = attribute(
        dtype='char',
        doc="1=LOCAL, 2=REALTIME, 3=RS232, 4=REMOTE1, 5=REMOTE2, 6=RS485, 7=PROFIBUS, 8=REMOTE3, 9=REMOTE4",
    )

    NominalCT = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
    )

    CT = attribute(
        dtype='double',
    )

    CL = attribute(
        dtype='double',
    )

    NominalCL = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
    )

    MathboxMode = attribute(
        dtype='char',
        access=AttrWriteType.READ_WRITE,
        max_value=5,
        min_value=1,
        doc="1=MANUAL, 2=AUTOMATIC, 3=REMOTE, 4=FREEZE, 5=DCAUTO",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(HuttingerPFGRF.init_device) ENABLED START #
        self.ser=serial.Serial(self.SerialPort,baudrate=9600,bytesize=8,parity="N",stopbits=1,timeout=0.5)
        (address,command,data)=self.parse_response(self.sendcommand(0,"CE",0))
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  HuttingerPFGRF.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(HuttingerPFGRF.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  HuttingerPFGRF.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(HuttingerPFGRF.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  HuttingerPFGRF.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_NominalPower(self):
        # PROTECTED REGION ID(HuttingerPFGRF.NominalPower_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"C1",0))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGRF.NominalPower_read

    def write_NominalPower(self, value):
        # PROTECTED REGION ID(HuttingerPFGRF.NominalPower_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"41",int(value)))
        # PROTECTED REGION END #    //  HuttingerPFGRF.NominalPower_write

    def read_NominalDCBias(self):
        # PROTECTED REGION ID(HuttingerPFGRF.NominalDCBias_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"C2",0))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGRF.NominalDCBias_read

    def write_NominalDCBias(self, value):
        # PROTECTED REGION ID(HuttingerPFGRF.NominalDCBias_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"42",int(value)))
        # PROTECTED REGION END #    //  HuttingerPFGRF.NominalDCBias_write

    def read_Channel(self):
        # PROTECTED REGION ID(HuttingerPFGRF.Channel_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"C7",0))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGRF.Channel_read

    def write_Channel(self, value):
        # PROTECTED REGION ID(HuttingerPFGRF.Channel_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"47",int(value)))
        # PROTECTED REGION END #    //  HuttingerPFGRF.Channel_write

    def read_RegulationMode(self):
        # PROTECTED REGION ID(HuttingerPFGRF.RegulationMode_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"CD",0))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGRF.RegulationMode_read

    def write_RegulationMode(self, value):
        # PROTECTED REGION ID(HuttingerPFGRF.RegulationMode_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"4D",int(value)))
        # PROTECTED REGION END #    //  HuttingerPFGRF.RegulationMode_write

    def read_IncidentPower(self):
        # PROTECTED REGION ID(HuttingerPFGRF.IncidentPower_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"D1",0))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGRF.IncidentPower_read

    def read_DCBias(self):
        # PROTECTED REGION ID(HuttingerPFGRF.DCBias_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"D2",0))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGRF.DCBias_read

    def read_ReflectedPower(self):
        # PROTECTED REGION ID(HuttingerPFGRF.ReflectedPower_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"D4",0))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGRF.ReflectedPower_read

    def read_Limit(self):
        # PROTECTED REGION ID(HuttingerPFGRF.Limit_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"D7",0))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGRF.Limit_read

    def write_Limit(self, value):
        # PROTECTED REGION ID(HuttingerPFGRF.Limit_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"57",int(value)))
        # PROTECTED REGION END #    //  HuttingerPFGRF.Limit_write

    def read_NominalRFPeakVoltage(self):
        # PROTECTED REGION ID(HuttingerPFGRF.NominalRFPeakVoltage_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"D8",0))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGRF.NominalRFPeakVoltage_read

    def write_NominalRFPeakVoltage(self, value):
        # PROTECTED REGION ID(HuttingerPFGRF.NominalRFPeakVoltage_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"58",int(value)))
        # PROTECTED REGION END #    //  HuttingerPFGRF.NominalRFPeakVoltage_write

    def read_RFPeakVoltage(self):
        # PROTECTED REGION ID(HuttingerPFGRF.RFPeakVoltage_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"D9",0))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGRF.RFPeakVoltage_read

    def read_Control(self):
        # PROTECTED REGION ID(HuttingerPFGRF.Control_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"CE",0))
        return(data)
        # PROTECTED REGION END #    //  HuttingerPFGRF.Control_read

    def read_NominalCT(self):
        # PROTECTED REGION ID(HuttingerPFGRF.NominalCT_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(1,"C5",0))
        return(data)
        # PROTECTED REGION END #    //  HuttingerPFGRF.NominalCT_read

    def write_NominalCT(self, value):
        # PROTECTED REGION ID(HuttingerPFGRF.NominalCT_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(1,"45",int(value)))
        # PROTECTED REGION END #    //  HuttingerPFGRF.NominalCT_write

    def read_CT(self):
        # PROTECTED REGION ID(HuttingerPFGRF.CT_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(1,"D5",0))
        return(data)
        # PROTECTED REGION END #    //  HuttingerPFGRF.CT_read

    def read_CL(self):
        # PROTECTED REGION ID(HuttingerPFGRF.CL_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(1,"D6",0))
        return(data)
        # PROTECTED REGION END #    //  HuttingerPFGRF.CL_read

    def read_NominalCL(self):
        # PROTECTED REGION ID(HuttingerPFGRF.NominalCL_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(1,"C6",0))
        return(data)
        # PROTECTED REGION END #    //  HuttingerPFGRF.NominalCL_read

    def write_NominalCL(self, value):
        # PROTECTED REGION ID(HuttingerPFGRF.NominalCL_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(1,"46",int(value)))
        return(data)
        # PROTECTED REGION END #    //  HuttingerPFGRF.NominalCL_write

    def read_MathboxMode(self):
        # PROTECTED REGION ID(HuttingerPFGRF.MathboxMode_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(1,"CD",0))
        return(data)
        # PROTECTED REGION END #    //  HuttingerPFGRF.MathboxMode_read

    def write_MathboxMode(self, value):
        # PROTECTED REGION ID(HuttingerPFGRF.MathboxMode_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(1,"4D",int(value)))
        return(data)
        # PROTECTED REGION END #    //  HuttingerPFGRF.MathboxMode_write


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def On(self):
        # PROTECTED REGION ID(HuttingerPFGRF.On) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"4F",1))
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  HuttingerPFGRF.On

    @command(
    )
    @DebugIt()
    def Off(self):
        # PROTECTED REGION ID(HuttingerPFGRF.Off) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"4F",0))
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  HuttingerPFGRF.Off

    @command(
    dtype_in=('str',), 
    dtype_out=('str',), 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def SendCmd(self, argin):
        # PROTECTED REGION ID(HuttingerPFGRF.SendCmd) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(int(argin[0]),argin[1],int(argin[2])))
        return([command+" %d"%data])
        # PROTECTED REGION END #    //  HuttingerPFGRF.SendCmd

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(HuttingerPFGRF.main) ENABLED START #
    return run((HuttingerPFGRF,), args=args, **kwargs)
    # PROTECTED REGION END #    //  HuttingerPFGRF.main

if __name__ == '__main__':
    main()
