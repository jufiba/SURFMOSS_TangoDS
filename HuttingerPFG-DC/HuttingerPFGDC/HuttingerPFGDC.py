# -*- coding: utf-8 -*-
#
# This file is part of the HuttingerPFGDC project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" HuttingerPFGDC

Driver for the Huttinger DC generators, such as the PFG-DC1500, a 1500W 1KV power supply for magnetron sputtering growth.
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
# PROTECTED REGION ID(HuttingerPFGDC.additionnal_import) ENABLED START #
import serial
import struct
# PROTECTED REGION END #    //  HuttingerPFGDC.additionnal_import

__all__ = ["HuttingerPFGDC", "main"]


class HuttingerPFGDC(Device):
    """
    Driver for the Huttinger DC generators, such as the PFG-DC1500, a 1500W 1KV power supply for magnetron sputtering growth.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(HuttingerPFGDC.class_variable) ENABLED START #
    
    def sendcommand(self,address,command,data):
        # Asume command is an string in hexadecimal, say C4
        # address is 0 for generator, 1 for matchbox
        cmd=struct.pack(">BBH",address,int(command,16),data)
        cmd_string=cmd+self.crc_code(cmd)
        self.ser.write(cmd_string)
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


    # PROTECTED REGION END #    //  HuttingerPFGDC.class_variable

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
        label="Nominal Power",
        unit="W",
        standard_unit="W",
        display_unit="W",
        max_value=150,
        min_value=0,
    )

    NominalVoltage = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        label="Nominal Voltage",
        unit="V",
        standard_unit="V",
        display_unit="V",
        format="%d",
        max_value=1000,
        min_value=0,
    )

    NominalCurrent = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        label="Nominal Current",
        unit="A",
        standard_unit="A",
        display_unit="A",
        format="%4.2f",
        max_value=3.5,
        min_value=0,
    )

    InitialPower = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        label="Initial Power",
        unit="W",
        standard_unit="W",
        display_unit="W",
        max_value=1500,
        min_value=0,
    )

    InitialVoltage = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        label="Initial Voltage",
        unit="V",
        standard_unit="V",
        display_unit="V",
        max_value=1000,
        min_value=0,
    )

    InitialCurrent = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        label="Initial Current",
        unit="A",
        standard_unit="A",
        display_unit="A",
        format="%4.2f",
    )

    VoltageRange = attribute(
        dtype='uint16',
        label="Voltage Range",
        max_value=4,
        min_value=1,
        doc="(1=375V, 2=500V, 3=750V, 4=1000V)",
    )

    ArcDetection = attribute(
        dtype='char',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        label="ArcDetection",
    )

    RampTime = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        label="RampTime",
        unit="s",
        standard_unit="s",
        display_unit="s",
        format="%4.1f",
        max_value=3200.0,
        min_value=0.0,
        doc="(1=power, 2=voltage, 3=current)",
    )

    ArcDetectionLevel = attribute(
        dtype='char',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        label="Level",
        max_value=3,
        min_value=1,
    )

    ArcDetectionPause = attribute(
        dtype='char',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        label="ArcDetectionPause",
        max_value=3,
        min_value=1,
    )

    RampType = attribute(
        dtype='char',
        access=AttrWriteType.READ_WRITE,
        label="RampType",
        max_value=3,
        min_value=1,
        doc="(1=power, 2=voltage, 3=current)",
    )

    Power = attribute(
        dtype='double',
        label="Power",
        unit="W",
        standard_unit="W",
        display_unit="W",
    )

    Voltage = attribute(
        dtype='double',
        label="Voltage",
        unit="V",
        standard_unit="V",
        display_unit="V",
    )

    Current = attribute(
        dtype='double',
        label="Current",
        unit="A",
        standard_unit="A",
        display_unit="A",
    )

    Arcs = attribute(
        dtype='double',
        display_level=DispLevel.EXPERT,
        label="Arcs",
    )

    OperationMode = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        label="OperationMode",
        max_value=2,
        min_value=0,
        doc="(0=OFF;1=On;\n2=On+Ramp)",
    )

    Control = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        max_value=5,
        min_value=1,
        doc="(1=LOCAL, 2=REALTIME,\n3=REMOTE, 4=RS232,\n5=RS485)",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(HuttingerPFGDC.init_device) ENABLED START #
        self.ser=serial.Serial(self.SerialPort,baudrate=9600,bytesize=8,parity="N",stopbits=1,timeout=0.5)
        (address,command,data)=self.parse_response(self.sendcommand(0,"4E",4))
        (address,command,data)=self.parse_response(self.sendcommand(0,"4F",0))
        self.set_state(PyTango.DevState.OFF)
        if (command!="ACK"):
                self.set_state(PyTango.DevState.FAULT)
        # PROTECTED REGION END #    //  HuttingerPFGDC.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(HuttingerPFGDC.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  HuttingerPFGDC.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(HuttingerPFGDC.delete_device) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"4F",0))
        self.ser.close()
        # PROTECTED REGION END #    //  HuttingerPFGDC.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_NominalPower(self):
        # PROTECTED REGION ID(HuttingerPFGDC.NominalPower_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"C1",0))
        return data*10
        # PROTECTED REGION END #    //  HuttingerPFGDC.NominalPower_read

    def write_NominalPower(self, value):
        # PROTECTED REGION ID(HuttingerPFGDC.NominalPower_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"41",int(value/10.0)))
        # PROTECTED REGION END #    //  HuttingerPFGDC.NominalPower_write

    def read_NominalVoltage(self):
        # PROTECTED REGION ID(HuttingerPFGDC.NominalVoltage_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"C2",4))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGDC.NominalVoltage_read

    def write_NominalVoltage(self, value):
        # PROTECTED REGION ID(HuttingerPFGDC.NominalVoltage_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"42",int(value)))
        # PROTECTED REGION END #    //  HuttingerPFGDC.NominalVoltage_write

    def read_NominalCurrent(self):
        # PROTECTED REGION ID(HuttingerPFGDC.NominalCurrent_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"C3",4))
        return data/100.0
        # PROTECTED REGION END #    //  HuttingerPFGDC.NominalCurrent_read

    def write_NominalCurrent(self, value):
        # PROTECTED REGION ID(HuttingerPFGDC.NominalCurrent_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"43",int(value*100.0)))
        # PROTECTED REGION END #    //  HuttingerPFGDC.NominalCurrent_write

    def read_InitialPower(self):
        # PROTECTED REGION ID(HuttingerPFGDC.InitialPower_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"C4",4))
        return data*10
        # PROTECTED REGION END #    //  HuttingerPFGDC.InitialPower_read

    def write_InitialPower(self, value):
        # PROTECTED REGION ID(HuttingerPFGDC.InitialPower_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"44",int(value/10)))
        # PROTECTED REGION END #    //  HuttingerPFGDC.InitialPower_write

    def read_InitialVoltage(self):
        # PROTECTED REGION ID(HuttingerPFGDC.InitialVoltage_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"C5",4))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGDC.InitialVoltage_read

    def write_InitialVoltage(self, value):
        # PROTECTED REGION ID(HuttingerPFGDC.InitialVoltage_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"45",int(value)))
        # PROTECTED REGION END #    //  HuttingerPFGDC.InitialVoltage_write

    def read_InitialCurrent(self):
        # PROTECTED REGION ID(HuttingerPFGDC.InitialCurrent_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"C6",4))
        return data/100.0
        # PROTECTED REGION END #    //  HuttingerPFGDC.InitialCurrent_read

    def write_InitialCurrent(self, value):
        # PROTECTED REGION ID(HuttingerPFGDC.InitialCurrent_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"46",int(value*100)))
        # PROTECTED REGION END #    //  HuttingerPFGDC.InitialCurrent_write

    def read_VoltageRange(self):
        # PROTECTED REGION ID(HuttingerPFGDC.VoltageRange_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"C8",4))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGDC.VoltageRange_read

    def read_ArcDetection(self):
        # PROTECTED REGION ID(HuttingerPFGDC.ArcDetection_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"C9",4))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGDC.ArcDetection_read

    def write_ArcDetection(self, value):
        # PROTECTED REGION ID(HuttingerPFGDC.ArcDetection_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"49",value))
        # PROTECTED REGION END #    //  HuttingerPFGDC.ArcDetection_write

    def read_RampTime(self):
        # PROTECTED REGION ID(HuttingerPFGDC.RampTime_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"CA",0))
        return data/10.0
        # PROTECTED REGION END #    //  HuttingerPFGDC.RampTime_read

    def write_RampTime(self, value):
        # PROTECTED REGION ID(HuttingerPFGDC.RampTime_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"4A",int(value*10.0)))
        # PROTECTED REGION END #    //  HuttingerPFGDC.RampTime_write

    def read_ArcDetectionLevel(self):
        # PROTECTED REGION ID(HuttingerPFGDC.ArcDetectionLevel_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"CB",4))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGDC.ArcDetectionLevel_read

    def write_ArcDetectionLevel(self, value):
        # PROTECTED REGION ID(HuttingerPFGDC.ArcDetectionLevel_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"4B",value))
        # PROTECTED REGION END #    //  HuttingerPFGDC.ArcDetectionLevel_write

    def read_ArcDetectionPause(self):
        # PROTECTED REGION ID(HuttingerPFGDC.ArcDetectionPause_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"CC",4))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGDC.ArcDetectionPause_read

    def write_ArcDetectionPause(self, value):
        # PROTECTED REGION ID(HuttingerPFGDC.ArcDetectionPause_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"4C",value))
        # PROTECTED REGION END #    //  HuttingerPFGDC.ArcDetectionPause_write

    def read_RampType(self):
        # PROTECTED REGION ID(HuttingerPFGDC.RampType_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"CD",4))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGDC.RampType_read

    def write_RampType(self, value):
        # PROTECTED REGION ID(HuttingerPFGDC.RampType_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"4D",value))
        # PROTECTED REGION END #    //  HuttingerPFGDC.RampType_write

    def read_Power(self):
        # PROTECTED REGION ID(HuttingerPFGDC.Power_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"D1",4))
        return data*10.0
        # PROTECTED REGION END #    //  HuttingerPFGDC.Power_read

    def read_Voltage(self):
        # PROTECTED REGION ID(HuttingerPFGDC.Voltage_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"D2",4))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGDC.Voltage_read

    def read_Current(self):
        # PROTECTED REGION ID(HuttingerPFGDC.Current_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"D3",4))
        return data/100.0
        # PROTECTED REGION END #    //  HuttingerPFGDC.Current_read

    def read_Arcs(self):
        # PROTECTED REGION ID(HuttingerPFGDC.Arcs_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"D9",4))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGDC.Arcs_read

    def read_OperationMode(self):
        # PROTECTED REGION ID(HuttingerPFGDC.OperationMode_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"CF",0))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGDC.OperationMode_read

    def write_OperationMode(self, value):
        # PROTECTED REGION ID(HuttingerPFGDC.OperationMode_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"4F",value))
        # PROTECTED REGION END #    //  HuttingerPFGDC.OperationMode_write

    def read_Control(self):
        # PROTECTED REGION ID(HuttingerPFGDC.Control_read) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"CE",0))
        return data
        # PROTECTED REGION END #    //  HuttingerPFGDC.Control_read

    def write_Control(self, value):
        # PROTECTED REGION ID(HuttingerPFGDC.Control_write) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"4E",value))
        # PROTECTED REGION END #    //  HuttingerPFGDC.Control_write


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def On(self):
        # PROTECTED REGION ID(HuttingerPFGDC.On) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"4F",2))
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  HuttingerPFGDC.On

    @command(
    )
    @DebugIt()
    def Off(self):
        # PROTECTED REGION ID(HuttingerPFGDC.Off) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"4F",0))
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  HuttingerPFGDC.Off

    @command(
    dtype_in=('str',), 
    dtype_out=('str',), 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def SendCmd(self, argin):
        # PROTECTED REGION ID(HuttingerPFGDC.SendCmd) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,argin[0],int(argin[1])))
        return([command+" %d"%data])
        # PROTECTED REGION END #    //  HuttingerPFGDC.SendCmd

    @command(
    )
    @DebugIt()
    def reset_arc_counter(self):
        # PROTECTED REGION ID(HuttingerPFGDC.reset_arc_counter) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"59",0))
        # PROTECTED REGION END #    //  HuttingerPFGDC.reset_arc_counter

    @command(
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def On_with_ramp(self):
        # PROTECTED REGION ID(HuttingerPFGDC.On_with_ramp) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"4F",1))
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  HuttingerPFGDC.On_with_ramp

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(HuttingerPFGDC.main) ENABLED START #
    return run((HuttingerPFGDC,), args=args, **kwargs)
    # PROTECTED REGION END #    //  HuttingerPFGDC.main

if __name__ == '__main__':
    main()
