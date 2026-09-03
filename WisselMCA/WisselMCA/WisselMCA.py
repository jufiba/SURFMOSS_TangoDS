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
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import device_property
from tango import AttrQuality, DispLevel, DevState
from tango import AttrWriteType
# Additional import
# PROTECTED REGION ID(WisselMCA.additionnal_import) ENABLED START #
import os
import sys
import time
import hid
import struct
import numpy

try:
    from .fold import fold, fold_at, curvature_ratio
except ImportError:          # run as a plain script, not as the package
    from fold import fold, fold_at, curvature_ratio

# Seconds to wait before trying the USB device again while in FAULT.
RETRY_PERIOD=10

class cmca:
    VendorID=0x0925
    InstrumentID=0x0035
    # The CMCA-550 talks in fixed 64-byte HID reports. A reply longer than
    # that arrives split across several of them.
    REPORT_SIZE=64

    def __init__(self):
        self.dev=hid.device()

    # Every reply gets a deadline. hid.device.read() without one waits for
    # ever on a blocking handle, and the whole device server waits with it:
    # the call runs inside the device's Tango serialization monitor, so ping
    # keeps answering while state() and every attribute come back IMP_LIMIT.
    # Found in exactly that state on 29-Aug-2026, six hours after a clean
    # restart, with a thread parked in hid_read_timeout / pthread_cond_wait
    # and not one USB error in dmesg: a single reply had gone missing, which
    # is all it takes. A second longer than the slowest reply is plenty.
    READ_TIMEOUT=1000

    def read_timed(self,nbytes):
        """One report, with a deadline. Empty means nothing arrived in time."""
        return self.dev.read(nbytes,self.READ_TIMEOUT)

    def resync(self):
        """Throw away what a lost or late reply left in the pipe.

        A reply that never came does not cost only that one command: it leaves
        the stream out of step, so every command after it reads the previous
        one's leftovers and reports a wrong count -- the desynchronisation
        read_response() below was written for. Draining here means the next
        command starts clean, and a card that will not go quiet says so
        instead of being waited on.
        """
        try:
            self.drain()
            return ""
        except Exception as e:
            return " (and %s)"%e

    def reply(self,nbytes,expect,what):
        """Read one reply, check its count byte, resynchronise on failure.

        (True, report) or (False, message), the shape checked() unwraps.
        """
        r=self.read_timed(nbytes)
        if not r:
            return(False,"no reply to %s in %d ms%s"
                   %(what,self.READ_TIMEOUT,self.resync()))
        if r[0]!=expect:
            note=self.resync()
            return(False,"wrong count in response %d%s"%(r[0],note))
        return(True,r)

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

    # Enough to clear anything a desynchronised session can have left, and
    # short enough that a card which never stops talking cannot hold the
    # device for ever. A full reply is two reports.
    DRAIN_REPORTS=64
    DRAIN_SECONDS=2.0

    def drain(self):
        """ Discard reports left queued by an earlier desynchronised session.

        Bounded, deliberately. This was `while self.dev.read(...)`, which never
        ends while the card keeps producing reports -- and a card that is
        measuring does. It runs inside the device's Tango serialization
        monitor, so the whole device wedges rather than the call failing: ping
        and info keep answering, while state() and every attribute come back
        "not able to acquire serialization monitor". Found in that state on
        29-Aug-2026 after twelve hours, at 0.7% CPU, which is what a 50 ms
        timeout in an endless loop looks like.
        """
        n=0
        end=time.monotonic()+self.DRAIN_SECONDS
        while n<self.DRAIN_REPORTS and time.monotonic()<end:
            if not self.dev.read(self.REPORT_SIZE,50):
                return n
            n+=1
        # Still talking after all that: say so rather than keep reading.
        raise IOError("the MCA is still sending after %d reports in %.1f s; "
                      "it did not go quiet to be drained" % (n, self.DRAIN_SECONDS))

    def open(self,path=None):
        """Open the card. By hidapi path if given, else by VendorID/InstrumentID.

        These cards report an empty serial number, so with two of them plugged
        in VendorID/InstrumentID cannot tell them apart and hidapi returns
        whichever it finds first. The path can: it encodes the USB topology,
        like the /dev/serial/by-path names the serial servers use.
        """
        if path:
            self.dev.open_path(path if isinstance(path,bytes)
                               else path.encode("ascii"))
        else:
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
        (ok,r)=self.reply(7,6,"model")
        if not ok:
            return(False,r)
        year=r[2]-0x48+2003
        week=r[3]
        serialnumber=r[4]*256+r[5]
        return(True,"%d %d %d"%(year,week,serialnumber))

    def start(self):
        self.dev.write(self.code(bytes([0x84]))) # Read mode
        (ok,r)=self.reply(4,3,"start/read mode")
        if not ok:
            return(False,r)
        self.dev.write(self.code(bytes([0x04,r[2]|0b00010000]))) # Set bit4 (Start)
        if not self.read_timed(4):
            return(False,"no reply to start/set mode in %d ms%s"
                   %(self.READ_TIMEOUT,self.resync()))
        # Re-checks the *first* reply, so it can never fail here. Left as it
        # was on purpose: correcting it changes what Start reports, and Start
        # is one of the two commands that touch a running measurement.
        if (r[0]!=3):
            return(False,"wrong count in response")
        return(True)

    def stop(self):
        self.dev.write(self.code(bytes([0x84]))) # Read mode
        (ok,r)=self.reply(4,3,"stop/read mode")
        if not ok:
            return(False,r)
        self.dev.write(self.code(bytes([0x04,r[2]&0b11101111]))) # Reset bit4 (Start)
        if not self.read_timed(4):
            return(False,"no reply to stop/set mode in %d ms%s"
                   %(self.READ_TIMEOUT,self.resync()))
        # Same as in start(): this re-checks the first reply. Left alone.
        if (r[0]!=3):
            return(False,"wrong count in response")
        return(True)

    def readgeneral(self):
        self.dev.write(self.code(bytes([0x81])))
        (ok,r)=self.reply(5,4,"readgeneral")
        if not ok:
            return(False,r)
        return(True,r[2]+256*r[3])

    def writegeneral(self,setupbytes):
        self.dev.write(self.code(bytes([0x01,setupbytes%256,setupbytes//256])))
        (ok,r)=self.reply(3,2,"writegeneral")
        if not ok:
            return(False,r)
        return(True)

    def setmode(self,mode):
        self.dev.write(self.code(bytes([0x04,mode])))
        (ok,r)=self.reply(3,2,"setmode")
        if not ok:
            return(False,r)
        return(True)

    def readmode(self):
        self.dev.write(self.code(bytes([0x84])))
        (ok,r)=self.reply(4,3,"readmode")
        if not ok:
            return(False,r)
        return(True,r[2])

    def cleardata(self):
        # Block 0 clears entire RAM for MCS and PHA
        self.dev.write(self.code(bytes([0x13,0])))
        (ok,r)=self.reply(3,2,"cleardata")
        if not ok:
            return(False,r)
        return(True)

    def readPHA(self):
        # Returns (True, array of 5 uint16): [Hysteresis, LLD1, ULD1, LLD2, ULD2]
        # Values are 14-bit: 0=0V, 16383=10V
        self.dev.write(self.code(bytes([0x88])))
        (ok,r)=self.reply(13,12,"readPHA")
        if not ok:
            return(False,r)
        w=numpy.frombuffer(bytes(r[2:12]),dtype="<u2")
        # w[0]=Hysteresis, w[1]=LLD1, w[2]=ULD1, w[3]=LLD2, w[4]=ULD2
        return(True,w)

    def writePHA(self,w): # w should be a uint16 array of 5 elements
        message=bytes([0x08])+w.tobytes()
        self.dev.write(self.code(message))
        (ok,r)=self.reply(3,2,"writePHA")
        if not ok:
            return(False,r)
        return(True)

    def readlastchannel(self):
        self.dev.write(self.code(bytes([0x92])))
        (ok,r)=self.reply(5,4,"readlastchannel")
        if not ok:
            return(False,r)
        chan=r[2]*256+r[3]
        return(True,chan)

    def readchannel(self,channel):
        # Channel number 0-8191; returns 32-bit count
        self.dev.write(self.code(bytes([0x91,channel//256,channel%256])))
        (ok,r)=self.reply(7,6,"readchannel")
        if not ok:
            return(False,r)
        chan=numpy.frombuffer(bytes(r[2:6]),dtype="<u4")
        return(True,int(chan[0]))

    def readpage(self,page):
        # Each page = 32 channels x 4 bytes = 128 bytes
        # pageH always 0 for pages 0-255
        # The 131-byte reply spans three HID reports, so it has to be reassembled
        self.dev.write(self.code(bytes([0x90,0,page])))
        r=self.read_response(131)
        if (len(r)<130):
            return(False,"short response to readpage, %d bytes%s"
                   %(len(r),self.resync()))
        if (r[0]!=130):
            return(False,"wrong count in response %d%s"%(r[0],self.resync()))
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

def phachannels(setup):
    """ Number of PHA channels implied by a General Setup word.

    Res[1:0] is bits 2-3 of setup byte 1, i.e. bits 10-11 of the word
    readgeneral() returns, and selects the ADC resolution: 13 bit = 8k
    channels, 12 bit = 4k, 11 bit = 2k, 10 bit = 1k (manual, page 3).

    Per page 4 the window limits are 14-bit *input voltages* (16383 = 10 V),
    not channel numbers, so the channel count cannot be read off them.
    """
    res=(setup>>10)&0b11
    return 8192>>res

def phalastchannel(setup,uld):
    """ How many channels are worth reading, given the upper window limit.

    The 14-bit window value spans the same 0-10 V input range as the channels,
    so channel = uld * channels / 16384, i.e. uld >> (1 + Res). Measured on the
    card: with Res=0 and ULD1 = 1310 (800 mV), the last channel holding counts
    is exactly 655 = 1310 >> 1.

    Pulses above the upper level are rejected, so stopping there loses nothing
    -- the total is identical whether 656 or all 8192 channels are read -- and
    it matters for speed: 8192 channels take 2.0 s against 0.17 s, and the
    former is uncomfortably close to the 3 s default client timeout in Tango.
    """
    n=phachannels(setup)
    res=(setup>>10)&0b11
    return min(int(uld)>>(1+res),n-1)+1

def channelwidth(setup):
    """ Width of one channel in mV, from a General Setup word.

    The window limits are 14-bit values over 0-10 V while the channels split
    the same range into 8192 >> Res, so one channel spans
    2**(1+Res) * 10000/16383 mV -- 1.2208 mV at the 13-bit default. Channel c
    starts at c * this; its centre is half a width further, a difference too
    small to matter next to the window settings but worth pinning down.
    """
    res=(setup>>10)&0b11
    return (1<<(1+res))*10000.0/16383

def checked(result,what):
    """ Unwrap a reply from cmca, raising a Tango error if it failed.

    Without this the error message travels on as if it were data and blows up
    somewhere else entirely, e.g. as a TypeError in an unrelated arithmetic.

    cmca is not consistent about its replies: the readers return (ok, value)
    but the writers return a bare True on success and (False, message) on
    failure, so both shapes have to be accepted.
    """
    if result is True:
        return None
    if result is False:
        result=(False,"no reply")
    (ok,value)=result
    if not ok:
        tango.Except.throw_exception("WisselMCA_CommError",
                                       "%s: %s"%(what,value),
                                       "WisselMCA."+what)
    return value

# PROTECTED REGION END #    //  WisselMCA.additionnal_import

__all__ = ["WisselMCA", "main"]


class WisselMCA(Device):
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

    DevicePath = device_property(
        dtype='str', default_value="",
        doc='Which card, when more than one is connected. The hidapi path, as '
            'hid.enumerate() reports it -- "1-1.1.2:1.0" on pi-rackmossbauer. '
            'Empty picks the first one matching VendorID and InstrumentID, '
            'which is right while there is only one. The serial number cannot '
            'be used for this: these cards report it empty.',
    )

    MCS_Channels = device_property(
        dtype='uint16', default_value=512,
        doc='Channels in one full native MCS sweep, i.e. one drive period. '
            '512 here, 256 on some setups. setMCAmode uses it as the channel '
            'count, and folding uses it as the N it folds over -- '
            'CalibrateFoldPoint and FoldedSpectrum need the whole sweep.',
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

    ChannelWidth = attribute(
        dtype='float',
        label="Channel Width",
        unit="mV",
        format="%6.4f",
        doc="Width of one Spectrum channel in mV, so that the spectrum can be "
            "plotted against the same scale the window limits use: channel c "
            "starts at c * ChannelWidth mV. PHA mode only — in MCS the "
            "channels are time bins and this reads INVALID.",
    )

    FoldedSpectrum = attribute(
        dtype=('double',),
        max_dim_x=4096,
        label="Folded Spectrum",
        standard_unit="counts",
        doc="The MCS spectrum folded about FoldPoint: "
            "folded[i] = raw[i] + raw[(FoldPoint - i) mod N], linearly "
            "interpolated, for i < N/2 (N = MCS_Channels). Recomputed on "
            "every read from the current raw sweep and the stored FoldPoint; "
            "it does NOT recalibrate. MCS analog mode and a full untruncated "
            "sweep only, otherwise it throws.",
    )

    FoldPoint = attribute(
        dtype='double',
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=False,
        label="Fold Point",
        format="%8.2f",
        doc="Mirror point for folding, in channels, near the sweep length N. "
            "Normally set by CalibrateFoldPoint; writable by hand for edge "
            "cases or to force a known value. Validated to N +/- 16.",
    )

    FoldPointAmbiguous = attribute(
        dtype='bool',
        label="Fold Point Ambiguous",
        doc="True when the last CalibrateFoldPoint found a flat mirror-chi2 "
            "minimum (curvature ratio < 0.02): the fold point is poorly "
            "determined, usually because too few counts have accumulated. "
            "False after a hand-set FoldPoint (no chi2 curve to judge).",
    )

    FoldPointCurvature = attribute(
        dtype='double',
        format="%7.4f",
        label="Fold Point Curvature",
        doc="Sharpness of the mirror-chi2 minimum: local curvature over the "
            "scan's overall range, the ratio CalibrateFoldPoint compares "
            "against 0.02. NaN until a calibration runs, and after a hand-set "
            "FoldPoint.",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(WisselMCA.init_device) ENABLED START #
        self.lastchannel = self.MCS_Channels
        self.firstchannel = 0
        self.lastconnect = 0
        # Default until CalibrateFoldPoint runs or the memorized FoldPoint is
        # written back: fold exactly on the sweep end.
        self.foldpoint = float(self.MCS_Channels)
        self.foldpoint_ambiguous = False
        self.foldpoint_curvature = float("nan")
        self.connect()
        # PROTECTED REGION END #    //  WisselMCA.init_device

    def connect(self):
        """ Open the MCA and pick up the mode it is in. True if it worked.

        Kept out of init_device because that runs exactly once: if the USB
        device was busy or not yet permitted at startup, the server used to
        stay FAULT for good, even when the instrument freed up a second later,
        and only an operator Init would recover it.
        """
        self.lastconnect = time.time()
        old = getattr(self, "c", None)
        if old is not None:
            try:
                old.close()   # or the stale handle keeps the USB to itself
            except Exception:
                pass
        self.c = cmca()
        self.c.VendorID = self.VendorID
        self.c.InstrumentID = self.InstrumentID
        try:
            self.c.open(self.DevicePath)
        except Exception as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't connect to Wissel MCA %x: %s"
                            % (self.InstrumentID, e))
            self.error_stream("Can't connect to Wissel MCA %x: %s"
                              % (self.InstrumentID, e))
            return False
        # Not `checked()` here: a comms error must not escape init_device, or
        # PyTango exits the whole server.
        (ok, modebyte) = self.c.readmode()
        if not ok:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Wissel MCA %x is open but does not answer: %s"
                            % (self.InstrumentID, modebyte))
            self.error_stream("Wissel MCA %x is open but does not answer: %s"
                              % (self.InstrumentID, modebyte))
            return False
        if modebyte & 0b00010000:
            self.set_state(tango.DevState.ON)   # counting
        else:
            self.set_state(tango.DevState.OFF)  # stopped
        mode = modebyte & 0b11
        self.firstchannel = 0
        if mode == 3:  # PHA mode
            (ok2, setup) = self.c.readgeneral()
            (ok3, w) = self.c.readPHA()
            if ok2 and ok3:
                self.lastchannel = phalastchannel(setup, w[2])
        else:  # MCS analog, MCS digital or None
            self.lastchannel = self.MCS_Channels
        self.set_status("Connected to Wissel MCA %x" % self.InstrumentID)
        self.debug_stream("Connected to Wissel MCA %x" % self.InstrumentID)
        return True

    def always_executed_hook(self):
        # PROTECTED REGION ID(WisselMCA.always_executed_hook) ENABLED START #
        # Tango runs this before every attribute access and command, so it is
        # where a device that was busy at startup gets picked up without an
        # operator Init. Rate-limited: a failed USB open is not free, and
        # callers should not pay for one on every single request.
        if (self.get_state() == tango.DevState.FAULT
                and time.time() - self.lastconnect > RETRY_PERIOD):
            self.connect()
        # PROTECTED REGION END #    //  WisselMCA.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(WisselMCA.delete_device) ENABLED START #
        try:
            self.c.close()
        except Exception:
            pass   # nothing to close if the open never succeeded
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
        checked(self.c.writePHA(rc), "writePHA")
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
        checked(self.c.writePHA(rc), "writePHA")
        # Moving the upper level moves where the counts stop, so the useful
        # length of the spectrum follows it.
        (ok, setup) = self.c.readgeneral()
        if ok:
            self.lastchannel = phalastchannel(setup, ch)
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
        checked(self.c.writePHA(rc), "writePHA")
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
        checked(self.c.writegeneral(value), "writegeneral")
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

    def read_ChannelWidth(self):
        # PROTECTED REGION ID(WisselMCA.ChannelWidth_read) ENABLED START #
        # Read live: the setup word is a 3-byte command, and this way nothing
        # goes stale if the resolution is changed by some other route. Do not
        # put this attribute on polling — it does not change on its own.
        setup = checked(self.c.readgeneral(), "readgeneral")
        w = channelwidth(setup)
        mode = checked(self.c.readmode(), "readmode") & 0b11
        if mode != 3:
            # MCS channels are time bins, so mV per channel is meaningless
            # there; say so rather than let a client label a time axis in mV.
            return (w, time.time(), tango.AttrQuality.ATTR_INVALID)
        return w
        # PROTECTED REGION END #    //  WisselMCA.ChannelWidth_read

    def _require_mcs_full_sweep(self, what):
        # PROTECTED REGION ID(WisselMCA._require_mcs_full_sweep) ENABLED START #
        """Guard for the folding paths: MCS analog mode and the whole native
        sweep, or a Tango error. Folding assumes a full drive period; on a
        truncated array fold()'s search can lock onto a wrong minimum and
        still look sharp (see fold.py's B5 note)."""
        mode = checked(self.c.readmode(), "readmode") & 0b11
        if mode != 2:
            tango.Except.throw_exception(
                "WisselMCA_NotMCSanalog",
                "%s needs MCS analog mode (triangular drive); mode is %d"
                % (what, mode),
                "WisselMCA." + what)
        if self.firstchannel != 0 or self.lastchannel < self.MCS_Channels - 1:
            tango.Except.throw_exception(
                "WisselMCA_WindowTruncated",
                "%s needs the full %d-channel sweep; the read window is "
                "%d..%d. Reset it with SetFirstChannel 0 and "
                "SetLastChannel %d." % (what, self.MCS_Channels,
                                        self.firstchannel, self.lastchannel,
                                        self.MCS_Channels),
                "WisselMCA." + what)
        # PROTECTED REGION END #    //  WisselMCA._require_mcs_full_sweep

    def _read_native_sweep(self):
        # PROTECTED REGION ID(WisselMCA._read_native_sweep) ENABLED START #
        """The whole 0..MCS_Channels raw spectrum as float, for folding."""
        d = checked(self.c.readspectrum_pages(0, self.MCS_Channels),
                    "readspectrum_pages")
        return numpy.asarray(d, dtype=float)
        # PROTECTED REGION END #    //  WisselMCA._read_native_sweep

    def read_FoldedSpectrum(self):
        # PROTECTED REGION ID(WisselMCA.FoldedSpectrum_read) ENABLED START #
        self._require_mcs_full_sweep("FoldedSpectrum")
        counts = self._read_native_sweep()
        return fold_at(counts, self.foldpoint)
        # PROTECTED REGION END #    //  WisselMCA.FoldedSpectrum_read

    def read_FoldPoint(self):
        # PROTECTED REGION ID(WisselMCA.FoldPoint_read) ENABLED START #
        return self.foldpoint
        # PROTECTED REGION END #    //  WisselMCA.FoldPoint_read

    def write_FoldPoint(self, value):
        # PROTECTED REGION ID(WisselMCA.FoldPoint_write) ENABLED START #
        n = self.MCS_Channels
        if not (n - 16 <= value <= n + 16):
            tango.Except.throw_exception(
                "WisselMCA_BadFoldPoint",
                "fold point %.3f is outside [%d, %d]; it sits near the sweep "
                "length %d" % (value, n - 16, n + 16, n),
                "WisselMCA.write_FoldPoint")
        self.foldpoint = float(value)
        # A hand-set point carries no chi2 curve to judge.
        self.foldpoint_ambiguous = False
        self.foldpoint_curvature = float("nan")
        # PROTECTED REGION END #    //  WisselMCA.FoldPoint_write

    def read_FoldPointAmbiguous(self):
        # PROTECTED REGION ID(WisselMCA.FoldPointAmbiguous_read) ENABLED START #
        return self.foldpoint_ambiguous
        # PROTECTED REGION END #    //  WisselMCA.FoldPointAmbiguous_read

    def read_FoldPointCurvature(self):
        # PROTECTED REGION ID(WisselMCA.FoldPointCurvature_read) ENABLED START #
        return self.foldpoint_curvature
        # PROTECTED REGION END #    //  WisselMCA.FoldPointCurvature_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def Start(self):
        # PROTECTED REGION ID(WisselMCA.Start) ENABLED START #
        checked(self.c.start(), "start")
        self.set_state(tango.DevState.ON)
        # PROTECTED REGION END #    //  WisselMCA.Start

    @command(
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(WisselMCA.Stop) ENABLED START #
        checked(self.c.stop(), "stop")
        self.set_state(tango.DevState.OFF)
        # PROTECTED REGION END #    //  WisselMCA.Stop

    @command(
    )
    @DebugIt()
    def setPHAmode(self):
        # PROTECTED REGION ID(WisselMCA.setPHAmode) ENABLED START #
        checked(self.c.setmode(3), "setmode")
        self.set_state(tango.DevState.OFF)
        self.firstchannel = 0
        setup = checked(self.c.readgeneral(), "readgeneral")
        w = checked(self.c.readPHA(), "readPHA")
        self.lastchannel = phalastchannel(setup, w[2])
        lower_mV = self.read_Lower_Window_Limit()
        upper_mV = self.read_Upper_Window_Limit()
        self.set_status("PHA mode, %d of %d channels, window %d - %d mV, "
                        "%.4f mV/channel"
                        % (self.lastchannel, phachannels(setup),
                           int(lower_mV), int(upper_mV), channelwidth(setup)))
        # PROTECTED REGION END #    //  WisselMCA.setPHAmode

    @command(
    )
    @DebugIt()
    def setMCAmode(self):
        # PROTECTED REGION ID(WisselMCA.setMCAmode) ENABLED START #
        checked(self.c.setmode(2), "setmode")
        self.firstchannel = 0
        self.lastchannel = self.MCS_Channels
        self.set_state(tango.DevState.OFF)
        self.set_status("MCS analog mode, %d channels" % self.MCS_Channels)
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
        checked(self.c.cleardata(), "cleardata")
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

    @command(
    )
    @DebugIt()
    def CalibrateFoldPoint(self):
        # PROTECTED REGION ID(WisselMCA.CalibrateFoldPoint) ENABLED START #
        # Run the offline pipeline's mirror-chi2 search over the full raw
        # sweep and store the result in FoldPoint. Call it once at the start
        # of a measurement (or again if the drive geometry/range changed) --
        # NOT in a loop: once fixed for a session the fold point must stay
        # put, or refolding on the fly adds noise and breaks reproducibility
        # within one acquisition.
        self._require_mcs_full_sweep("CalibrateFoldPoint")
        counts = self._read_native_sweep()
        _folded, F, robustness, _Fs, resid = fold(counts)
        self.foldpoint = float(F)
        self.foldpoint_ambiguous = (robustness == "flat")
        self.foldpoint_curvature = curvature_ratio(resid)
        self.set_status(
            "Fold point %.2f over %d channels (%s, curvature %.4f)%s"
            % (self.foldpoint, len(counts), robustness,
               self.foldpoint_curvature,
               " -- TOO FEW COUNTS, not reliable yet"
               if self.foldpoint_ambiguous else ""))
        # PROTECTED REGION END #    //  WisselMCA.CalibrateFoldPoint

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
