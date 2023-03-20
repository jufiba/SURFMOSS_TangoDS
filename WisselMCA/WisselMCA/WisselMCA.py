# -*- coding: utf-8 -*-
#
# This file is part of the WisselMCA project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" WisselMCA

Device server for the Wissel Multichannel Analyzer used for Mossbauer spectroscopy.
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
# PROTECTED REGION ID(WisselMCA.additionnal_import) ENABLED START #
import hid
import struct
import numpy

class cmca:
    VendorID=0x0925
    InstrumentID=0x0035
    dev=hid.device()
    
    def open(self):
        #self.dev=hid.device()
        self.dev.open(self.VendorID,self.InstrumentID)
        self.dev.set_nonblocking(False)
        return(True)

    def close(self):
        self.dev.close()
        return(True)
        
    def crc(self,a):
        result=0
        for i in range(0,len(a)):
            result+= a[i]
        return(bytes([int.to_bytes(result,2,"little")[0]]))

    def code(self, message):
        l=bytes([len(message)+1])
        c=self.crc(l+message)
        full_message=l+message+c
        return(full_message)

    def model(self):
        self.dev.write(self.code(bytes([0xF1])))
        r=self.dev.read(7)
        if (r[0]!=6):
            return(False,"wrong count in response")
        year=r[2]-0x48+2003
        week=r[3]
        serialnumber=r[4]*256+r[5]
        return(True,"%d %d %d"%(year,week,serialnumber))

    def start(self):
        self.dev.write(self.code(bytes([0x84]))) #Read mo
        r=self.dev.read(4)
        if (r[0]!=3):                        
            return(False, "wrong count in response")
        self.dev.write(self.code(bytes([0x04,r[2]|0b00010000]))) # Set bit4
        self.dev.read(4) # Doc is wrong. Response is same as for read
        if (r[0]!=3):
            return(False,"wrong count in response")
        return(True)
       
    def stop(self):
        self.dev.write(self.code(bytes([0x84]))) #Read mode
        r=self.dev.read(4)
        if (r[0]!=3):
            return(False)
        self.dev.write(self.code(bytes([0x04,r[2]&0b11101111]))) # Reset Bit4
        self.dev.read(4) # Doc is wrong. Response is same as for read
        if (r[0]!=3):
            return(False,"wrong count in response")
        return(True)
    
    def readgeneral(self):
        self.dev.write(self.code(bytes([0x81]))) 
        r=self.dev.read(5)
        if (r[0]!=4):                        
            return(False, "wrong count in response %d"%r[0])
        return(True,r[2]+256*r[3])
    
    def writegeneral(self,setupbytes):
        self.dev.write(self.code(bytes([0x01,setupbytes%256,setupbytes//256]))) 
        r=self.dev.read(3)
        if (r[0]!=2):                        
            return(False, "wrong count in response %d"%r[0])
        return(True)
        
    def setmode(self,mode):
        self.dev.write(self.code(bytes([0x04,mode])))
        r=self.dev.read(3) # Doc is wrong. Response is same as for read
        if (r[0]!=2):
            return(False,"wrong count in response %d"%r[0])
        return(True)
        
    def readmode(self):
        self.dev.write(self.code(bytes([0x84]))) 
        r=self.dev.read(4)
        if (r[0]!=3):                        
            return(False, "wrong count in response %d"%r[0])
        return(True,r[2])
    
    def cleardata(self):
        self.dev.write(self.code(bytes([0x13,0]))) # Clear all RAM
        r=self.dev.read(3) # Doc is wrong. Response is same as for read
        if (r[0]!=2):
            return(False,"wrong count in response")
        return(True)

    def readPHA(self):
        self.dev.write(self.code(bytes([0x88])))
        r=self.dev.read(13)
        if (r[0]!=12):
            return(False,"")
        w=numpy.frombuffer(bytes(r[2:12]),dtype="<u2")
        #w[0]= hyst, w[1]=lowerLevel_LowerWindow, w[2]=upperLevel_LowerWindow,w[3]=lowerLevel_UpperWindow, w[4]=upperLevel_UpperWindow
        return(True,w)

    def writePHA(self,w): # w should be a int array
        message=bytes([0x08])+w.tobytes()
        self.dev.write(self.code(message))
        r=self.dev.read(3)
        if (r[0]!=2):
            return(False,"wrong count in response %d"%r[0])
        return(True)
    
    def readlastchannel(self): #
        self.dev.write(self.code(bytes([0x92])))
        r=self.dev.read(5)
        if (r[0]!=4):
            return(False,"wrong count in response %d"%r[0])
        chan=r[3]+r[2]*256
        return(True,chan)
    
    def readchannel(self,channel):
        self.dev.write(self.code(bytes([0x91,channel//256,channel%256])))
        r=self.dev.read(7)
        if (r[0]!=6):
            return(False,"wrong count in response %d"%r[0])
        chan=numpy.frombuffer(bytes(r[2:6]),dtype="<u4")
        return(True,chan[0])
        
    def readpage(self,page):
        self.dev.write(self.code(bytes([0x90,0,page])))
        r=self.dev.read(131)
        if (r[0]!=130):
            return(False,"wrong count in response %d"%r[0])
        #chan=numpy.frombuffer(bytes(r[2:130]),dtype="<u4")
        return(True,bytes(r[2:130]))

    def readspectrum(self,l0,l1):
        data=numpy.zeros(l1-l0)	
        for i in range(l0,l1):
           (status,data[i])=self.readchannel(i-l0)
           if (status!=True):
              return(False,"problem reading channel %d"%i)
        return(True,data)

# PROTECTED REGION END #    //  WisselMCA.additionnal_import

__all__ = ["WisselMCA", "main"]


class WisselMCA(Device):
    """
    Device server for the Wissel Multichannel Analyzer used for Mossbauer spectroscopy.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(WisselMCA.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  WisselMCA.class_variable

    # -----------------
    # Device Properties
    # -----------------

    VendorID = device_property(
        dtype='uint16', default_value=0x0925
    )

    InstrumentID = device_property(
        dtype='uint16', default_value=0x0035
    )

    # ----------
    # Attributes
    # ----------

    Lower_Window_Limit = attribute(
        dtype='float',
        access=AttrWriteType.READ_WRITE,
        label="Window Lower Limit",
        unit="mV",
        format="%5.0f",
        max_value=10000,
        min_value=0,
        doc="Window lower limit of windows in channels. 16383 channels = l0 Volts, so 0.61mV/channel.",
    )

    Upper_Window_Limit = attribute(
        dtype='float',
        access=AttrWriteType.READ_WRITE,
        label="Window Upper Limit",
        unit="mV",
        format="%5.0f",
        max_value=10000,
        min_value=0,
    )

    Model = attribute(
        dtype='str',
        display_level=DispLevel.EXPERT,
    )

    Configuration = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
    )

    LastChannel = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
    )

    ModeByte = attribute(
        dtype='uint16',
        display_level=DispLevel.EXPERT,
    )

    Mode = attribute(
        dtype='DevEnum',
        enum_labels=["None", "AnalogMCA", "MCA", "PHA", ],
    )

    Spectrum = attribute(
        dtype=('uint64',),
        max_dim_x=8192,
        standard_unit="counts",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(WisselMCA.init_device) ENABLED START #
        self.lastchannel= numpy.ushort(512)
        self.firstchannel= numpy.ushort(0)
        self.c=cmca()
        self.c.VendorID=self.VendorID
        self.c.InstrumentID=self.InstrumentID
        try:
            self.c.open()
        except:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Can't connect to Wissel MCA %x"%self.InstrumentID)
            self.debug_stream("Can't connect to Wissel MCA %x"%self.InstrumentID)
            return
        mode=self.c.readmode()
        if (mode[1]&0b10000):
            self.set_state(PyTango.DevState.ON)
        else:
            self.set_state(PyTango.DevState.OFF)
        self.set_status("Connected to Wissel MCA %x"%self.InstrumentID)
        self.debug_stream("Connected to Wissel MCA %x"%self.InstrumentID)
        m=self.read_Mode
        if (mode==3): # We are in PHA mode
            self.firstchannel=self.read_Lower_Window_Limit()*16383/20000
            self.lastchannel=self.read_Upper_Window_Limit()*16383/20000
        elif (mode==2): # We are in MCA mode
            self.firstchannel=0
            self.lastchannel=512
        # PROTECTED REGION END #    //  WisselMCA.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(WisselMCA.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WisselMCA.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(WisselMCA.delete_device) ENABLED START #
        self.c.close()
        # PROTECTED REGION END #    //  WisselMCA.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Lower_Window_Limit(self):
        # PROTECTED REGION ID(WisselMCA.Lower_Window_Limit_read) ENABLED START #
        (t,r)=self.c.readPHA()
        w=float(r[1]*10000/16383)
        return w
        # PROTECTED REGION END #    //  WisselMCA.Lower_Window_Limit_read

    def write_Lower_Window_Limit(self, value):
        # PROTECTED REGION ID(WisselMCA.Lower_Window_Limit_write) ENABLED START #
        (t,r)=self.c.readPHA()
        rc=r.copy()
        rc[1]=numpy.ushort(16383*value/10000) # Translate from mV to channel, 1383 channels are 10V
        self.c.writePHA(rc)
        # PROTECTED REGION END #    //  WisselMCA.Lower_Window_Limit_write

    def read_Upper_Window_Limit(self):
        # PROTECTED REGION ID(WisselMCA.Upper_Window_Limit_read) ENABLED START #
        (t,r)=self.c.readPHA()
        w=float(r[2]*10000/16383)
        return w
        # PROTECTED REGION END #    //  WisselMCA.Upper_Window_Limit_read

    def write_Upper_Window_Limit(self, value):
        # PROTECTED REGION ID(WisselMCA.Upper_Window_Limit_write) ENABLED START #
        (t,r)=self.c.readPHA()
        rc=r.copy()
        rc[2]=rc[3]=rc[4]=numpy.ushort(value*16383/10000)
        self.c.writePHA(rc)
        # PROTECTED REGION END #    //  WisselMCA.Upper_Window_Limit_write

    def read_Model(self):
        # PROTECTED REGION ID(WisselMCA.Model_read) ENABLED START #
        (t,r)=self.c.model()
        return r
        # PROTECTED REGION END #    //  WisselMCA.Model_read

    def read_Configuration(self):
        # PROTECTED REGION ID(WisselMCA.Configuration_read) ENABLED START #
        (t,r)=self.c.readgeneral()
        return r
        # PROTECTED REGION END #    //  WisselMCA.Configuration_read

    def write_Configuration(self, value):
        # PROTECTED REGION ID(WisselMCA.Configuration_write) ENABLED START #
        self.c.writegeneral(value)
        # PROTECTED REGION END #    //  WisselMCA.Configuration_write

    def read_LastChannel(self):
        # PROTECTED REGION ID(WisselMCA.LastChannel_read) ENABLED START #
        return self.lastchannel
        # PROTECTED REGION END #    //  WisselMCA.LastChannel_read

    def write_LastChannel(self, value):
        # PROTECTED REGION ID(WisselMCA.LastChannel_write) ENABLED START #
        self.lastchannel=numpy.ushort(value)
        # PROTECTED REGION END #    //  WisselMCA.LastChannel_write

    def read_ModeByte(self):
        # PROTECTED REGION ID(WisselMCA.ModeByte_read) ENABLED START #
        (t,r)=self.c.readmode()
        return r
        # PROTECTED REGION END #    //  WisselMCA.ModeByte_read

    def read_Mode(self):
        # PROTECTED REGION ID(WisselMCA.Mode_read) ENABLED START #
        (t,r)=self.c.readmode()
        m=int(r&0b11)
        return m
        # PROTECTED REGION END #    //  WisselMCA.Mode_read

    def read_Spectrum(self):
        # PROTECTED REGION ID(WisselMCA.Spectrum_read) ENABLED START #
        (t,d)=self.c.readspectrum(self.firstchannel,self.lastchannel)
        return d
        # PROTECTED REGION END #    //  WisselMCA.Spectrum_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def Start(self):
        # PROTECTED REGION ID(WisselMCA.Start) ENABLED START #
        self.set_state(PyTango.DevState.ON)
        self.c.start()
        # PROTECTED REGION END #    //  WisselMCA.Start

    @command(
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(WisselMCA.Stop) ENABLED START #
        self.set_state(PyTango.DevState.OFF)
        self.c.stop()
        # PROTECTED REGION END #    //  WisselMCA.Stop

    @command(
    )
    @DebugIt()
    def setPHAmode(self):
        # PROTECTED REGION ID(WisselMCA.setPHAmode) ENABLED START #
        self.c.setmode(3)
        self.set_state(PyTango.DevState.OFF)
        self.firstchannel=self.read_Lower_Window_Limit()*16383/20000
        self.lastchannel=self.read_Upper_Window_Limit()*16383/20000
        self.set_status("Entering PHA mode, with window %d %d"%(self.firstchannel,self.lastchannel))
        # PROTECTED REGION END #    //  WisselMCA.setPHAmode

    @command(
    )
    @DebugIt()
    def setMCAmode(self):
        # PROTECTED REGION ID(WisselMCA.setMCAmode) ENABLED START #
        self.c.setmode(2)
        self.firstchannel=0
        self.lastchannel=512
        self.set_state(PyTango.DevState.OFF)
        self.set_status("Entering PHA mode, with window %d %d"%(0,512))
        # PROTECTED REGION END #    //  WisselMCA.setMCAmode

    @command(
    dtype_in='uint16', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def SetLastChannel(self, argin):
        # PROTECTED REGION ID(WisselMCA.SetLastChannel) ENABLED START #
        self.lastchannel=numpy.uint(argin)
        # PROTECTED REGION END #    //  WisselMCA.SetLastChannel

    @command(
    )
    @DebugIt()
    def ClearMem(self):
        # PROTECTED REGION ID(WisselMCA.ClearMem) ENABLED START #
        self.c.cleardata()
        # PROTECTED REGION END #    //  WisselMCA.ClearMem

    @command(
    dtype_in='uint16', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def SetFirstChannel(self, argin):
        # PROTECTED REGION ID(WisselMCA.SetFirstChannel) ENABLED START #
        self.firstchannel=numpy.uint(argin)
        # PROTECTED REGION END #    //  WisselMCA.SetFirstChannel

    @command(
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def ReadLastChannel(self):
        # PROTECTED REGION ID(WisselMCA.ReadLastChannel) ENABLED START #
        (t,r)=self.c.readlastchannel()
        self.lastchannel=numpy.ushort(r+1) # Number of channels is lastchannel+1, as first channel is 0.
        # PROTECTED REGION END #    //  WisselMCA.ReadLastChannel

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(WisselMCA.main) ENABLED START #
    return run((WisselMCA,), args=args, **kwargs)
    # PROTECTED REGION END #    //  WisselMCA.main

if __name__ == '__main__':
    main()
