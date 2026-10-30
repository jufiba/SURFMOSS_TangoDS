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
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import device_property
from tango import AttrQuality, DispLevel, DevState
from tango import AttrWriteType
# Additional import
# PROTECTED REGION ID(HuttingerPFGDC.additionnal_import) ENABLED START #
import os
import sys
import serial
import struct


# Control modes, from the manual's table 8.12, row N. Only RS232 lets this
# server command anything; the rest answer queries and refuse writes.
MODE_RS232 = 3
MODE_NAMES = {1: "LOCAL", 2: "REALTIME", 3: "RS232", 4: "REMOTE1",
              5: "REMOTE2", 6: "RS485", 7: "PROFIBUS", 8: "REMOTE3",
              9: "REMOTE4"}


class HuttingerError(Exception):
    """The generator did not answer, or answered something that is not a
    frame. One exception for every way the exchange can fail, because to
    every caller they mean the same thing: there is no reading to be had.
    Same shape as LeyboldIG3's IG3Error."""


# PROTECTED REGION END #    //  HuttingerPFGDC.additionnal_import

__all__ = ["HuttingerPFGDC", "main"]


class HuttingerPFGDC(Device):
    """
    Driver for the Huttinger DC generators, such as the PFG-DC1500, a 1500W 1KV power supply for magnetron sputtering growth.
    """
    # PROTECTED REGION ID(HuttingerPFGDC.class_variable) ENABLED START #

    def sendcommand(self,address,command,data):
        # Asume command is an string in hexadecimal, say C4
        # address is 0 for generator, 1 for matchbox
        cmd=struct.pack(">BBH",address,int(command,16),data)
        cmd_string=cmd+self.crc_code(cmd)
        self.ser.write(cmd_string)
        return(self.ser.read(5))

    def parse_response(self,resp):
        # The length check has to come before the unpack. A short or empty
        # reply used to reach struct.unpack and raise "unpack requires a
        # buffer of 5 bytes", which says nothing about which port, which
        # command, or whether anything came back at all -- and a silent
        # generator returns b"", so that is the likely case, not the exotic
        # one. On 30-oct-2026 sputtering/power/magDC showed exactly that
        # message for a cable with no null-modem adapter: nothing was
        # arriving, and the status blamed a buffer.
        if (len(resp)!=5):
            raise HuttingerError("expected a 5-byte block, got %d: %r"
                                 %(len(resp),resp))
        # The checksum is the XOR of the first four bytes (manual, table 8.12,
        # "5 byte communication block"). Verified against the live generator:
        # 00^4e^00^02 = 4c, which is what it answers to CE.
        crc=0
        for b in resp[:4]:
            crc^=b
        if (crc!=resp[4]):
            raise HuttingerError("checksum mismatch on %r: computed %02x, "
                                 "received %02x"%(resp,crc,resp[4]))
        (address,cmd,data,crc)=struct.unpack(">BBHB",resp)
        cmd=resp[1]
        if (cmd==21):
            command="NACK"
        elif (cmd==6):
            command="ACK"
        else:
            command="%x"%resp[1]
        return(address,command,data)

    def byte_hex(self,a):
         return("%02x"%a)

    def crc_code(self,a):
         result=0
         for i in range(0,len(a)):
            result = result ^ a[i]
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
        # An exception escaping init_device makes PyTango exit the whole
        # server, and the Starter then leaves it for dead: a switched-off
        # instrument took the process with it instead of leaving a device that
        # says why. FAULT, not OFF -- OFF is used below for an instrument that
        # answers and has its output disabled, which is a different fact.
        self.ser=None
        try:
            self.ser=serial.Serial(self.SerialPort,baudrate=9600,bytesize=8,parity="N",stopbits=1,timeout=0.5)
        except (serial.SerialException,ValueError) as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't open %s: %s"%(self.SerialPort,e))
            self.error_stream("Can't open %s: %s"%(self.SerialPort,e))
            return
        # Start-up ASKS, it does not command. What was here before sent two
        # writes: 4E with data 4 (set control mode) and 4F with data 0 (set
        # operating state OFF). Both were wrong:
        #
        #   - 4F=0 switches the output off. Starting a device server, or an
        #     Init from Jive, must not drop a generator somebody is using.
        #     HuttingerPFGRF never did this: it opens with a single CE query.
        #   - the control mode was set to 4 = REMOTE1, which is control over
        #     the I/O connector. Driving it over the serial line wants
        #     3 = RS232 (manual, table 8.12, row N). Confirmed against the
        #     PFG-DC on 30-oct-2026: writing 3 is ACKed and reads back as 3.
        #
        # CE is the read-only counterpart of 4E: the top bit of the function
        # byte is the manual's "wait bit", which tells a query from a write,
        # so every query is its write command | 0x80.
        try:
            (address,command,mode)=self.parse_response(self.sendcommand(0,"CE",0))
        except Exception as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("No usable answer on %s: %s"%(self.SerialPort,e))
            self.error_stream("No usable answer on %s: %s"%(self.SerialPort,e))
            return
        # The mode is reported, not imposed. Putting the generator into RS232
        # is a decision with a plant attached -- it takes control away from
        # whoever has the front panel -- so it belongs in an explicit command,
        # not in init_device. SetRemoteControl does it.
        self.controlmode=mode
        self.set_state(tango.DevState.OFF)
        if (mode==MODE_RS232):
            self.set_status("Connected to the PFG-DC, control mode RS232")
        else:
            self.set_status("Connected to the PFG-DC, but control mode is %s "
                            "(%d), not RS232: it will answer queries and "
                            "refuse commands. SetRemoteControl changes it."
                            %(MODE_NAMES.get(mode,"unknown"),mode))
        # PROTECTED REGION END #    //  HuttingerPFGDC.init_device
    def always_executed_hook(self):
        # PROTECTED REGION ID(HuttingerPFGDC.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  HuttingerPFGDC.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(HuttingerPFGDC.delete_device) ENABLED START #
        # Reached now on a device whose port never opened, and the exchange
        # below cannot work if the supply is the reason it did not.
        if (self.ser is None):
            return
        # Switching the output off on the way out is DELIBERATE here, and is
        # the opposite decision from init_device on purpose. A generator left
        # running with nothing watching it is the dangerous state; a generator
        # switched off when the server stops is merely inconvenient. The same
        # reasoning as the deadman in FUGMCP and Itech6000C, done the simple
        # way because this supply has no deadman of its own.
        #
        # An Init from Jive calls delete_device too, so an Init does drop the
        # output. That is worth knowing before using Init on a running
        # deposition.
        try:
            (address,command,data)=self.parse_response(self.sendcommand(0,"4F",0))
        except Exception as e:
            self.debug_stream("Could not reset the supply before closing: %s"%e)
        self.ser.close()
        # PROTECTED REGION END #    //  HuttingerPFGDC.delete_device
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
        self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  HuttingerPFGDC.On

    @command(
    )
    @DebugIt()
    def Off(self):
        # PROTECTED REGION ID(HuttingerPFGDC.Off) ENABLED START #
        (address,command,data)=self.parse_response(self.sendcommand(0,"4F",0))
        self.set_state(tango.DevState.OFF)
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
        self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  HuttingerPFGDC.On_with_ramp

    @command(
    dtype_out='str',
    display_level=DispLevel.EXPERT,
    doc_out="the control mode in force afterwards",
    )
    @DebugIt()
    def SetRemoteControl(self):
        # PROTECTED REGION ID(HuttingerPFGDC.SetRemoteControl) ENABLED START #
        return self.do_set_remote_control()
        # PROTECTED REGION END #    //  HuttingerPFGDC.SetRemoteControl

    def do_set_remote_control(self):
        """Put the generator into RS232 control, and say what it ended up in.

        This is what init_device used to do by itself, wrongly and silently.
        It is a command now because it takes control away from whoever has
        the front panel, and that is a decision for a person: starting a
        device server is not a request to seize an instrument.

        Split out of the @command body so the tests can drive it: @DebugIt()
        wants a real Tango logger, which a stubbed Device has not got. Same
        split as AnalogInterlock.do_reset and LeyboldIG3.do_start.
        """
        self.parse_response(self.sendcommand(0,"4E",MODE_RS232))
        # Read it back rather than assume the write took: on this generator a
        # refused write answers NAK and the mode simply stays as it was.
        (address,command,mode)=self.parse_response(self.sendcommand(0,"CE",0))
        self.controlmode=mode
        name=MODE_NAMES.get(mode,"unknown")
        if (mode!=MODE_RS232):
            self.set_status("The generator refused RS232 control and stayed "
                            "in %s (%d)"%(name,mode))
            return "refused: still %s (%d)"%(name,mode)
        self.set_status("Connected to the PFG-DC, control mode RS232")
        return "RS232"

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(HuttingerPFGDC.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((HuttingerPFGDC,), args=args, **kwargs)
    # PROTECTED REGION END #    //  HuttingerPFGDC.main

if __name__ == '__main__':
    main()
