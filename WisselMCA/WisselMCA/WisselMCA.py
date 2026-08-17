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
import os
import sys
import hid
import struct
import numpy

class cmca:
    VendorID=0x0925
    InstrumentID=0x0035
    # The CMCA-550 talks in fixed 64-byte HID reports. A reply longer than
    # that arrives split across several of them.
    REPORT_SIZE=64

    def __init__(self):
        self.dev=hid.device()

    def read_response(self,nbytes,timeout=1000):
        """ Read a reply of nbytes, reassembling it from 64-byte HID reports.

        Asking hid for more than one report's worth returns only the first
        one and leaves the rest queued, which desynchronises every command
        that follows: each one then reads the previous reply's leftovers and
        reports a wrong count. Keep reading until the reply is complete.
        """
        buf=bytearray()
        while len(buf)<nbytes:
            r=self.dev.read(self.REPORT_SIZE,timeout)
            if not r:
                break
            buf.extend(r)
        return buf

    def drain(self):
        """ Discard reports left queued by an earlier desynchronised session. """
        n=0
        while self.dev.read(self.REPORT_SIZE,50):
            n+=1
        return n

    def open(self):
        self.dev.open(self.VendorID,self.InstrumentID)
        self.dev.set_nonblocking(False)
        self.drain()
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
        self.dev.write(self.code(bytes([0x84]))) # Read mode
        r=self.dev.read(4)
        if (r[0]!=3):
            return(False, "wrong count in response")
        self.dev.write(self.code(bytes([0x04,r[2]|0b00010000]))) # Set bit4 (Start)
        self.dev.read(4)
        if (r[0]!=3):
            return(False,"wrong count in response")
        return(True)

    def stop(self):
        self.dev.write(self.code(bytes([0x84]))) # Read mode
        r=self.dev.read(4)
        if (r[0]!=3):
            return(False)
        self.dev.write(self.code(bytes([0x04,r[2]&0b11101111]))) # Reset bit4 (Start)
        self.dev.read(4)
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
        r=self.dev.read(3)
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
        # Block 0 clears entire RAM for MCS and PHA
        self.dev.write(self.code(bytes([0x13,0])))
        r=self.dev.read(3)
        if (r[0]!=2):
            return(False,"wrong count in response")
        return(True)

    def readPHA(self):
        # Returns (True, array of 5 uint16): [Hysteresis, LLD1, ULD1, LLD2, ULD2]
        # Values are 14-bit: 0=0V, 16383=10V
        self.dev.write(self.code(bytes([0x88])))
        r=self.dev.read(13)
        if (r[0]!=12):
            return(False,"wrong count in response")
        w=numpy.frombuffer(bytes(r[2:12]),dtype="<u2")
        # w[0]=Hysteresis, w[1]=LLD1, w[2]=ULD1, w[3]=LLD2, w[4]=ULD2
        return(True,w)

    def writePHA(self,w): # w should be a uint16 array of 5 elements
        message=bytes([0x08])+w.tobytes()
        self.dev.write(self.code(message))
        r=self.dev.read(3)
        if (r[0]!=2):
            return(False,"wrong count in response %d"%r[0])
        return(True)

    def readlastchannel(self):
        self.dev.write(self.code(bytes([0x92])))
        r=self.dev.read(5)
        if (r[0]!=4):
            return(False,"wrong count in response %d"%r[0])
        chan=r[2]*256+r[3]
        return(True,chan)

    def readchannel(self,channel):
        # Channel number 0-8191; returns 32-bit count
        self.dev.write(self.code(bytes([0x91,channel//256,channel%256])))
        r=self.dev.read(7)
        if (r[0]!=6):
            return(False,"wrong count in response %d"%r[0])
        chan=numpy.frombuffer(bytes(r[2:6]),dtype="<u4")
        return(True,int(chan[0]))

    def readpage(self,page):
        # Each page = 32 channels x 4 bytes = 128 bytes
        # pageH always 0 for pages 0-255
        # The 131-byte reply spans three HID reports, so it has to be reassembled
        self.dev.write(self.code(bytes([0x90,0,page])))
        r=self.read_response(131)
        if (len(r)<130):
            return(False,"short response, %d bytes"%len(r))
        if (r[0]!=130):
            return(False,"wrong count in response %d"%r[0])
        return(True,bytes(r[2:130]))

    def readspectrum_pages(self, first_channel=0, n_channels=256):
        # Fast spectrum read using page transfers (32 channels per page)
        # first_channel must be a multiple of 32
        first_page = first_channel // 32
        n_pages = (n_channels + 31) // 32
        data = numpy.zeros(n_pages * 32, dtype=numpy.uint64)
        for i in range(n_pages):
            (status, raw) = self.readpage(first_page + i)
            if not status:
                return (False, "problem reading page %d" % (first_page + i))
            page_data = numpy.frombuffer(raw, dtype='<u4')
            data[i*32:(i+1)*32] = page_data
        return (True, data[:n_channels])

    def readspectrum(self, l0, l1):
        # Slow channel-by-channel read; use readspectrum_pages for better performance
        data = numpy.zeros(l1-l0, dtype=numpy.uint64)
        for i in range(l0, l1):
            (status, val) = self.readchannel(i)
            if not status:
                return (False, "problem reading channel %d" % i)
            data[i-l0] = val
        return (True, data)

def checked(result,what):
    """ Unwrap a (ok,value) reply from cmca, raising a Tango error if it failed.

    Without this the error message travels on as if it were data and blows up
    somewhere else entirely, e.g. as a TypeError in an unrelated arithmetic.
    """
    (ok,value)=result
    if not ok:
        PyTango.Except.throw_exception("WisselMCA_CommError",
                                       "%s: %s"%(what,value),
                                       "WisselMCA."+what)
    return value

# PROTECTED REGION END #    //  WisselMCA.additionnal_import

__all__ = ["WisselMCA", "main"]


class WisselMCA(Device, metaclass=DeviceMeta):
    """
    Device server for the Wissel Multichannel Analyzer used for Mossbauer spectroscopy.
    """
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
        doc="Lower level of lower window in mV. 16383 channels = 10 Volts.",
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

    Hysteresis = attribute(
        dtype='float',
        access=AttrWriteType.READ_WRITE,
        label="Hysteresis",
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
        enum_labels=["None", "MCS_digital", "MCS_analog", "PHA"],
    )

    Spectrum = attribute(
        dtype=('uint64',),
        max_dim_x=8192,
        label="Spectrum",
        standard_unit="counts",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(WisselMCA.init_device) ENABLED START #
        self.lastchannel = 512
        self.firstchannel = 0
        self.c = cmca()
        self.c.VendorID = self.VendorID
        self.c.InstrumentID = self.InstrumentID
        try:
            self.c.open()
        except Exception as e:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Can't connect to Wissel MCA %x: %s"
                            % (self.InstrumentID, e))
            self.error_stream("Can't connect to Wissel MCA %x: %s"
                              % (self.InstrumentID, e))
            return
        (ok, modebyte) = self.c.readmode()
        if ok:
            if modebyte & 0b00010000:
                self.set_state(PyTango.DevState.ON)   # counting
            else:
                self.set_state(PyTango.DevState.OFF)  # stopped
            mode = modebyte & 0b11
            if mode == 3:  # PHA mode
                self.firstchannel = 0
                (ok2, w) = self.c.readPHA()
                if ok2:
                    # ULD1 already comes in the 14-bit units setPHAmode calls
                    # channels, so it must not be scaled again — and the uint16
                    # multiply overflowed anyway.
                    self.lastchannel = int(w[2])
            elif mode == 2:  # MCS analog
                self.firstchannel = 0
                self.lastchannel = 512
            else:  # MCS digital or None
                self.firstchannel = 0
                self.lastchannel = 512
        self.set_status("Connected to Wissel MCA %x" % self.InstrumentID)
        self.debug_stream("Connected to Wissel MCA %x" % self.InstrumentID)
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
        r = checked(self.c.readPHA(), "readPHA")
        return float(r[1]) * 10000 / 16383  # LLD1 in mV
        # PROTECTED REGION END #    //  WisselMCA.Lower_Window_Limit_read

    def write_Lower_Window_Limit(self, value):
        # PROTECTED REGION ID(WisselMCA.Lower_Window_Limit_write) ENABLED START #
        r = checked(self.c.readPHA(), "readPHA")
        rc = r.copy()
        rc[1] = numpy.uint16(round(16383 * value / 10000))  # LLD1
        self.c.writePHA(rc)
        # PROTECTED REGION END #    //  WisselMCA.Lower_Window_Limit_write

    def read_Upper_Window_Limit(self):
        # PROTECTED REGION ID(WisselMCA.Upper_Window_Limit_read) ENABLED START #
        r = checked(self.c.readPHA(), "readPHA")
        return float(r[2]) * 10000 / 16383  # ULD1 in mV
        # PROTECTED REGION END #    //  WisselMCA.Upper_Window_Limit_read

    def write_Upper_Window_Limit(self, value):
        # PROTECTED REGION ID(WisselMCA.Upper_Window_Limit_write) ENABLED START #
        r = checked(self.c.readPHA(), "readPHA")
        rc = r.copy()
        ch = numpy.uint16(round(value * 16383 / 10000))
        rc[2] = rc[3] = rc[4] = ch  # ULD1=LLD2=ULD2 (single window mode per protocol)
        self.c.writePHA(rc)
        # PROTECTED REGION END #    //  WisselMCA.Upper_Window_Limit_write

    def read_Hysteresis(self):
        # PROTECTED REGION ID(WisselMCA.Hysteresis_read) ENABLED START #
        r = checked(self.c.readPHA(), "readPHA")
        return float(r[0]) * 10000 / 16383
        # PROTECTED REGION END #    //  WisselMCA.Hysteresis_read

    def write_Hysteresis(self, value):
        # PROTECTED REGION ID(WisselMCA.Hysteresis_write) ENABLED START #
        r = checked(self.c.readPHA(), "readPHA")
        rc = r.copy()
        rc[0] = numpy.uint16(round(value * 16383 / 10000))
        self.c.writePHA(rc)
        # PROTECTED REGION END #    //  WisselMCA.Hysteresis_write

    def read_Model(self):
        # PROTECTED REGION ID(WisselMCA.Model_read) ENABLED START #
        r = checked(self.c.model(), "model")
        return r
        # PROTECTED REGION END #    //  WisselMCA.Model_read

    def read_Configuration(self):
        # PROTECTED REGION ID(WisselMCA.Configuration_read) ENABLED START #
        r = checked(self.c.readgeneral(), "readgeneral")
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
        self.lastchannel = int(value)
        # PROTECTED REGION END #    //  WisselMCA.LastChannel_write

    def read_ModeByte(self):
        # PROTECTED REGION ID(WisselMCA.ModeByte_read) ENABLED START #
        r = checked(self.c.readmode(), "readmode")
        return r
        # PROTECTED REGION END #    //  WisselMCA.ModeByte_read

    def read_Mode(self):
        # PROTECTED REGION ID(WisselMCA.Mode_read) ENABLED START #
        r = checked(self.c.readmode(), "readmode")
        return int(r & 0b11)
        # PROTECTED REGION END #    //  WisselMCA.Mode_read

    def read_Spectrum(self):
        # PROTECTED REGION ID(WisselMCA.Spectrum_read) ENABLED START #
        n_channels = self.lastchannel - self.firstchannel
        d = checked(self.c.readspectrum_pages(self.firstchannel, n_channels), "readspectrum_pages")
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
        self.c.start()
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  WisselMCA.Start

    @command(
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(WisselMCA.Stop) ENABLED START #
        self.c.stop()
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  WisselMCA.Stop

    @command(
    )
    @DebugIt()
    def setPHAmode(self):
        # PROTECTED REGION ID(WisselMCA.setPHAmode) ENABLED START #
        self.c.setmode(3)
        self.set_state(PyTango.DevState.OFF)
        self.firstchannel = 0
        upper_mV = self.read_Upper_Window_Limit()
        self.lastchannel = int(round(upper_mV * 16383 / 10000))
        self.set_status("PHA mode, window 0 - %d channels (0 - %d mV)" % (self.lastchannel, int(upper_mV)))
        # PROTECTED REGION END #    //  WisselMCA.setPHAmode

    @command(
    )
    @DebugIt()
    def setMCAmode(self):
        # PROTECTED REGION ID(WisselMCA.setMCAmode) ENABLED START #
        self.c.setmode(2)
        self.firstchannel = 0
        self.lastchannel = 512
        self.set_state(PyTango.DevState.OFF)
        self.set_status("MCS analog mode, 512 channels")
        # PROTECTED REGION END #    //  WisselMCA.setMCAmode

    @command(
    dtype_in='uint16',
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def SetLastChannel(self, argin):
        # PROTECTED REGION ID(WisselMCA.SetLastChannel) ENABLED START #
        self.lastchannel = int(argin)
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
        self.firstchannel = int(argin)
        # PROTECTED REGION END #    //  WisselMCA.SetFirstChannel

    @command(
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def ReadLastChannel(self):
        # PROTECTED REGION ID(WisselMCA.ReadLastChannel) ENABLED START #
        r = checked(self.c.readlastchannel(), "readlastchannel")
        self.lastchannel = int(r) + 1  # lastchannel+1 = number of channels (first channel is 0)
        # PROTECTED REGION END #    //  WisselMCA.ReadLastChannel

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(WisselMCA.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((WisselMCA,), args=args, **kwargs)
    # PROTECTED REGION END #    //  WisselMCA.main

if __name__ == '__main__':
    main()
