# -*- coding: utf-8 -*-
#
# This file is part of the ElmitecLEEM2k project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" ElmitecLEEM2k

Device server for accessing the settings of the LEEM2000 program from Elmitec.
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
# PROTECTED REGION ID(ElmitecLEEM2k.additionnal_import) ENABLED START #
import socket


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False
# PROTECTED REGION END #    //  ElmitecLEEM2k.additionnal_import

__all__ = ["ElmitecLEEM2k", "main"]


class ElmitecLEEM2k(Device):
    """
    Device server for accessing the settings of the LEEM2000 program from Elmitec.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(ElmitecLEEM2k.class_variable) ENABLED START #
    ElmitecLEEM2kConnected = False

    def TCPBlockingReceive(self):
        Bytereceived = '0'
        szData = ''
        while ord(Bytereceived) != 0:
            ReceivedLength = 0
            while ReceivedLength == 0:
                Bytereceived = self.s.recv(1)
                #print 'Bytereceived=',Bytereceived,'ord(Bytereceived)=',ord(Bytereceived)
                ReceivedLength = len(Bytereceived)
            if ord(Bytereceived) != 0:
                szData = szData + Bytereceived
        return szData

    def connect(self):
        if self.ElmitecLEEM2kConnected:
            return
        else:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                #self.s.connect((self.IP, self.Port))
                self.s.connect(("leem.labo",5566))
            except:
                self.ElmitecLEEM2kConnected = False
                self.set_state(PyTango.DevState.FAULT)
                self.set_status("Can't connect to ElmitecLEEM2k")
                self.debug_stream("Can't connect to ElmitecLEEM2k")
                return
            #Start string communication
            TCPString = 'asc'
            self.s.send(TCPString)
            data = self.TCPBlockingReceive()
            self.ElmitecLEEM2kConnected = True
            self.set_state(PyTango.DevState.ON)
            self.set_status("Connected to ElmitecLEEM2k")
            self.debug_stream("Connected to ElmitecLEEM2k")

    def disconnect(self):
        if self.ElmitecLEEM2kConnected:
            self.s.send('clo')
            self.s.close()
            self.ElmitecLEEM2kConnected = False
            self.debug_stream("Disconnected!")
    # PROTECTED REGION END #    //  ElmitecLEEM2k.class_variable

    # -----------------
    # Device Properties
    # -----------------

    IP = device_property(
        dtype='str',
    )

    Port = device_property(
        dtype='uint16',
    )

    # ----------
    # Attributes
    # ----------

    Objective = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        standard_unit="mA",
    )

    Preset = attribute(
        dtype='str',
        access=AttrWriteType.READ_WRITE,
    )

    StartVoltage = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        standard_unit="V",
    )

    TransferLens = attribute(
        dtype='double',
        standard_unit="mA",
    )

    FieldLens = attribute(
        dtype='double',
        standard_unit="mA",
    )

    IntermLens = attribute(
        dtype='double',
        standard_unit="mA",
    )

    P1Lens = attribute(
        dtype='double',
        standard_unit="mA",
    )

    P2Lens = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        standard_unit="mA",
    )

    SampleTemperature = attribute(
        dtype='double',
        standard_unit="ºC",
    )

    ChannelPlateVoltage = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        standard_unit="kV",
    )

    BombVoltage = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
    )

    IllDefX = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        unit="mA",
    )

    IllDefY = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        unit="mA",
    )

    IllEqX = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        unit="mA",
    )

    IllEqY = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        unit="mA",
    )

    ImEqX = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        unit="mA",
    )

    ImEqY = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        unit="mA",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(ElmitecLEEM2k.init_device) ENABLED START #
        self.connect()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  ElmitecLEEM2k.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.delete_device) ENABLED START #
        self.disconnect()
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Objective(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.Objective_read) ENABLED START #
        self.s.send("val 11")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.Objective_read

    def write_Objective(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.Objective_write) ENABLED START #
        self.s.send("val 11 "+str(value))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.Objective_write

    def read_Preset(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.Preset_read) ENABLED START #
        self.s.send("prl")
        data = self.TCPBlockingReceive()
        return data
        # PROTECTED REGION END #    //  ElmitecLEEM2k.Preset_read

    def write_Preset(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.Preset_write) ENABLED START #
        #self.s.send("sep "+str(value))
        #data = self.TCPBlockingReceive()
        #return data
        pass
        # PROTECTED REGION END #    //  ElmitecLEEM2k.Preset_write

    def read_StartVoltage(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.StartVoltage_read) ENABLED START #
        self.s.send("val 38")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.StartVoltage_read

    def write_StartVoltage(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.StartVoltage_write) ENABLED START #
        self.s.send("val 38 "+str(value))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.StartVoltage_write

    def read_TransferLens(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.TransferLens_read) ENABLED START #
        self.s.send("val 14")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.TransferLens_read

    def read_FieldLens(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.FieldLens_read) ENABLED START #
        self.s.send("val 19")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.FieldLens_read

    def read_IntermLens(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.IntermLens_read) ENABLED START #
        self.s.send("val 21")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IntermLens_read

    def read_P1Lens(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.P1Lens_read) ENABLED START #
        self.s.send("val 24")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.P1Lens_read

    def read_P2Lens(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.P2Lens_read) ENABLED START #
        self.s.send("val 27")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.P2Lens_read

    def write_P2Lens(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.P2Lens_write) ENABLED START #
        self.s.send("val 27 "+str(value))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.P2Lens_write

    def read_SampleTemperature(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.SampleTemperature_read) ENABLED START #
        self.s.send("val 39")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.SampleTemperature_read

    def read_ChannelPlateVoltage(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.ChannelPlateVoltage_read) ENABLED START #
        self.s.send("val 105")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.ChannelPlateVoltage_read

    def write_ChannelPlateVoltage(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.ChannelPlateVoltage_write) ENABLED START #
        self.s.send("val 105 "+str(value))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.ChannelPlateVoltage_write

    def read_BombVoltage(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.BombVoltage_read) ENABLED START #
        self.s.send("val 41")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecLEEM2k.BombVoltage_read

    def write_BombVoltage(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.BombVoltage_write) ENABLED START #
        self.s.send("val 41 "+str(value))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.BombVoltage_write

    def read_IllDefX(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllDefX_read) ENABLED START #
        self.s.send("val 2")
        data = self.TCPBlockingReceive()
        return float(data)   
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllDefX_read

    def write_IllDefX(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllDefX_write) ENABLED START #
        self.s.send("val 2 "+str(value))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllDefX_write

    def read_IllDefY(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllDefY_read) ENABLED START #
        self.s.send("val 3")
        data = self.TCPBlockingReceive()
        return float(data)        
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllDefY_read

    def write_IllDefY(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllDefY_write) ENABLED START #
        self.s.send("val 3 "+str(value))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllDefY_write

    def read_IllEqX(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllEqX_read) ENABLED START #
        self.s.send("val 30")
        data = self.TCPBlockingReceive()
        return float(data)        
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllEqX_read

    def write_IllEqX(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllEqX_write) ENABLED START #
        self.s.send("val 30 "+str(value))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllEqX_write

    def read_IllEqY(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllEqY_read) ENABLED START #
        self.s.send("val 31")
        data = self.TCPBlockingReceive()
        return float(data)        
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllEqY_read

    def write_IllEqY(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.IllEqY_write) ENABLED START #
        self.s.send("val 31 "+str(value))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.IllEqY_write

    def read_ImEqX(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.ImEqX_read) ENABLED START #
        self.s.send("val 33")
        data = self.TCPBlockingReceive()
        return float(data)        
        # PROTECTED REGION END #    //  ElmitecLEEM2k.ImEqX_read

    def write_ImEqX(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.ImEqX_write) ENABLED START #
        self.s.send("val 33 "+str(value))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.ImEqX_write

    def read_ImEqY(self):
        # PROTECTED REGION ID(ElmitecLEEM2k.ImEqY_read) ENABLED START #
        self.s.send("val 34")
        data = self.TCPBlockingReceive()
        return float(data)        
        # PROTECTED REGION END #    //  ElmitecLEEM2k.ImEqY_read

    def write_ImEqY(self, value):
        # PROTECTED REGION ID(ElmitecLEEM2k.ImEqY_write) ENABLED START #
        self.s.send("val 34 "+str(value))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecLEEM2k.ImEqY_write


    # --------
    # Commands
    # --------

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def sendCommand(self, argin):
        # PROTECTED REGION ID(ElmitecLEEM2k.sendCommand) ENABLED START #
        self.s.send(argin)
        data = self.TCPBlockingReceive()
        return data
        # PROTECTED REGION END #    //  ElmitecLEEM2k.sendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(ElmitecLEEM2k.main) ENABLED START #
    return run((ElmitecLEEM2k,), args=args, **kwargs)
    # PROTECTED REGION END #    //  ElmitecLEEM2k.main

if __name__ == '__main__':
    main()
