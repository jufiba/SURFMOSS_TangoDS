# -*- coding: utf-8 -*-
#
# This file is part of the ElmitecUview project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" ElmitecUview

Device server reads data from PEEM end station. UView must be running.
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
# PROTECTED REGION ID(ElmitecUview.additionnal_import) ENABLED START #
import numpy
import socket


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False
# PROTECTED REGION END #    //  ElmitecUview.additionnal_import

__all__ = ["ElmitecUview", "main"]


class ElmitecUview(Device):
    """
    Device server reads data from PEEM end station. UView must be running.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(ElmitecUview.class_variable) ENABLED START #
    ElmitecUviewConnected = False

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
        if self.ElmitecUviewConnected:
            return
        else:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                #self.s.connect((self.ElmitecUviewIP, self.ElmitecUviewPort))
                self.s.connect(("leem.labo",5570))
            except:
                self.ElmitecUviewConnected = False
                self.set_state(PyTango.DevState.FAULT)
                self.set_status("Can't connect to ElmitecUview")
                self.debug_stream("Can't connect to ElmitecUview")
                return
            #Start string communication
            TCPString = 'asc'
            self.s.send(TCPString)
            data = self.TCPBlockingReceive()
            self.ElmitecUviewConnected = True
            self.set_state(PyTango.DevState.ON)
            self.set_status("Connected to ElmitecUview")
            self.debug_stream("Connected to ElmitecUview")

    def disconnect(self):
        if self.ElmitecUviewConnected:
            self.s.send('clo')
            self.s.close()
            self.ElmitecUviewConnected = False
            self.debug_stream("Disconnected!")

    def getROIdata(self, ROIid):
        self.connect()
        if self.ElmitecUviewConnected:
            TCPString = 'roi ' + str(ROIid)
            try:
                self.s.send(TCPString)
                data = self.TCPBlockingReceive()
            except:
                self.ElmitecUviewConnected = False
                self.set_state(PyTango.DevState.FAULT)
                self.set_status("Can't read from ElmitecUview")
                self.debug_stream("Can't read fom ElmitecUview")
                return None
            if is_number(data):
                self.debug_stream("Correct reading of IntensityROI" + str(ROIid))
                return float(data)
            else:
                self.debug_stream("Incorrect numeric value of IntensityROI" + str(ROIid))
                return None
        else:
            self.debug_stream("No connection with ElmitecUview")
            return None
    # PROTECTED REGION END #    //  ElmitecUview.class_variable

    # -----------------
    # Device Properties
    # -----------------

    UviewIP = device_property(
        dtype='str', default_value="10.10.99.29"
    )

    UviewPort = device_property(
        dtype='uint', default_value=5570
    )

    # ----------
    # Attributes
    # ----------

    IntensityROI1 = attribute(
        dtype='double',
    )

    Exposure = attribute(
        dtype='float',
        access=AttrWriteType.READ_WRITE,
        standard_unit="ms",
    )

    Average = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
    )

    AcquisitionInProgress = attribute(
        dtype='bool',
    )

    ImageWidth = attribute(
        dtype='uint16',
    )

    ImageHeight = attribute(
        dtype='uint16',
    )

    Binning = attribute(
        dtype='uint16',
    )

    ContinousAcquisition = attribute(
        dtype='bool',
        access=AttrWriteType.WRITE,
        memorized=True,
        hw_memorized=True,
    )

    ImageData = attribute(
        dtype=(('uint16',),),
        max_dim_x=1024, max_dim_y=1024,
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        self.set_change_event("IntensityROI1", True, False)
        # PROTECTED REGION ID(ElmitecUview.init_device) ENABLED START #
        self.connect()
        # PROTECTED REGION END #    //  ElmitecUview.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(ElmitecUview.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  ElmitecUview.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(ElmitecUview.delete_device) ENABLED START #
        self.disconnect()
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  ElmitecUview.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_IntensityROI1(self):
        # PROTECTED REGION ID(ElmitecUview.IntensityROI1_read) ENABLED START #
        return self.getROIdata(1)
        # PROTECTED REGION END #    //  ElmitecUview.IntensityROI1_read

    def read_Exposure(self):
        # PROTECTED REGION ID(ElmitecUview.Exposure_read) ENABLED START #
        self.s.send("ext")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecUview.Exposure_read

    def write_Exposure(self, value):
        # PROTECTED REGION ID(ElmitecUview.Exposure_write) ENABLED START #
        self.s.send("ext "+str(value))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecUview.Exposure_write

    def read_Average(self):
        # PROTECTED REGION ID(ElmitecUview.Average_read) ENABLED START #
        self.s.send("avr")
        data = self.TCPBlockingReceive()
        return int(data)
        # PROTECTED REGION END #    //  ElmitecUview.Average_read

    def write_Average(self, value):
        # PROTECTED REGION ID(ElmitecUview.Average_write) ENABLED START #
        self.s.send("avr "+str(value))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecUview.Average_write

    def read_AcquisitionInProgress(self):
        # PROTECTED REGION ID(ElmitecUview.AcquisitionInProgress_read) ENABLED START #
        self.s.send("aip")
        data = self.TCPBlockingReceive()
        return int(data)
        # PROTECTED REGION END #    //  ElmitecUview.AcquisitionInProgress_read

    def read_ImageWidth(self):
        # PROTECTED REGION ID(ElmitecUview.ImageWidth_read) ENABLED START #
        self.s.send("giw")
        data = self.TCPBlockingReceive()
        return int(data)
        # PROTECTED REGION END #    //  ElmitecUview.ImageWidth_read

    def read_ImageHeight(self):
        # PROTECTED REGION ID(ElmitecUview.ImageHeight_read) ENABLED START #
        self.s.send("gih")
        data = self.TCPBlockingReceive()
        return int(data)
        # PROTECTED REGION END #    //  ElmitecUview.ImageHeight_read

    def read_Binning(self):
        # PROTECTED REGION ID(ElmitecUview.Binning_read) ENABLED START #
        self.s.send("bin")
        data = self.TCPBlockingReceive()
        return int(data.split()[0])
        # PROTECTED REGION END #    //  ElmitecUview.Binning_read

    def write_ContinousAcquisition(self, value):
        # PROTECTED REGION ID(ElmitecUview.ContinousAcquisition_write) ENABLED START #
        self.s.send("aip "+str(int(value)))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecUview.ContinousAcquisition_write

    def read_ImageData(self):
        # PROTECTED REGION ID(ElmitecUview.ImageData_read) ENABLED START #
        #self.s.send("ida 0 0 ")
        #data = self.s.revc(19)
        #print data
        #totalchar=int(data[1:8])
        #width=int(data[9:13])
        #height=int(data[14:18])
        #self.s.revc(totalchar)
        #dump=data[19:]
        #print totalchar,",",width,"x",height
        #dt = np.dtype(short)
        #dt = dt.newbyteorder('>')
        #datadump=numpy.frombuffer(dump,dtype=dt)
        #datadump.reshape((width,height))
        #print datadump.shape()
        #return datadump
        pass
        # PROTECTED REGION END #    //  ElmitecUview.ImageData_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def AcquireSingleImage(self):
        # PROTECTED REGION ID(ElmitecUview.AcquireSingleImage) ENABLED START #
        self.s.send("asi -1")
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecUview.AcquireSingleImage

    @command(
    dtype_in='str', 
    dtype_out='str', 
    )
    @DebugIt()
    def SaveImageAsDAT(self, argin):
        # PROTECTED REGION ID(ElmitecUview.SaveImageAsDAT) ENABLED START #
        self.s.send("exp 0,0,"+argin)
        data = self.TCPBlockingReceive()
        return(data)
        # PROTECTED REGION END #    //  ElmitecUview.SaveImageAsDAT

    @command(
    dtype_in='str', 
    dtype_out='str', 
    )
    @DebugIt()
    def SaveImageAsPNG(self, argin):
        # PROTECTED REGION ID(ElmitecUview.SaveImageAsPNG) ENABLED START #
        self.s.send("exp 1,2,"+argin)
        data = self.TCPBlockingReceive()
        return(data)
        # PROTECTED REGION END #    //  ElmitecUview.SaveImageAsPNG

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def sendCommand(self, argin):
        # PROTECTED REGION ID(ElmitecUview.sendCommand) ENABLED START #
        self.s.send(argin)
        data = self.TCPBlockingReceive()
        return data
        # PROTECTED REGION END #    //  ElmitecUview.sendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(ElmitecUview.main) ENABLED START #
    return run((ElmitecUview,), args=args, **kwargs)
    # PROTECTED REGION END #    //  ElmitecUview.main

if __name__ == '__main__':
    main()
