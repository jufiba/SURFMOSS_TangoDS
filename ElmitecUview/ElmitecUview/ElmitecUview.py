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
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import device_property
from tango import AttrQuality, DispLevel, DevState
from tango import AttrWriteType
# Additional import
# PROTECTED REGION ID(ElmitecUview.additionnal_import) ENABLED START #
import os
import sys
import socket
import threading


class ElmitecUviewError(Exception):
    """UView is not there, or stopped answering part way through an exchange."""


class _Reconnect(threading.Thread):
    """Rebuild the link while it is down, so a restart of UView does
    not need this server restarted too.

    UView is restarted often, and until now each restart meant
    restarting this device server by hand.
    """

    def __init__(self, ds):
        threading.Thread.__init__(self, daemon=True)
        self.ds = ds
        self.stop = threading.Event()

    def run(self):
        while not self.stop.wait(self.ds.ReconnectPeriod):
            if not self.ds.ElmitecUviewConnected:
                self.ds.connect()
# import numpy  # re-add when ImageData_read is implemented


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
    # PROTECTED REGION ID(ElmitecUview.class_variable) ENABLED START #
    ElmitecUviewConnected = False

    def TCPBlockingReceive(self):
        """One reply, up to the NUL that ends it, or ElmitecUviewError.

        The old loop spun on `while ReceivedLength == 0: recv(1)`. On a blocking
        socket recv returns at least one byte, or zero only at end of file, so
        when UView was restarted and the connection went away this
        turned into a busy loop at full CPU that never ended -- which is why
        the server had to be restarted by hand rather than recovering.
        """
        szData = ''
        while True:
            try:
                Bytereceived = self.s.recv(1)
            except OSError as e:
                self._drop("UView stopped answering: %s" % e)
                raise ElmitecUviewError("UView stopped answering: %s" % e)
            if not Bytereceived:
                self._drop("UView closed the connection")
                raise ElmitecUviewError("UView closed the connection")
            if Bytereceived == b'\x00':
                return szData
            szData = szData + Bytereceived.decode("ascii")

    def _send(self, data):
        """Send, and mark the link down if it fails so it gets rebuilt."""
        if not self.ElmitecUviewConnected:
            raise ElmitecUviewError("not connected to UView at %s:%d"
                                  % (self.IP, self.Port))
        try:
            self.s.send(data)
        except OSError as e:
            self._drop("could not send to UView: %s" % e)
            raise ElmitecUviewError("could not send to UView: %s" % e)

    def _drop(self, why):
        """Forget the connection; the reconnect thread will rebuild it."""
        self.ElmitecUviewConnected = False
        try:
            self.s.close()
        except Exception:                                     # noqa: BLE001
            pass
        self.set_state(tango.DevState.FAULT)
        self.set_status(why)
        self.error_stream(why)

    def connect(self):
        """Open the link and start string mode. True if it is up.

        Everything past the connect() used to be outside the try, so a program
        that accepted the connection and then said nothing took the whole
        server down from init_device.
        """
        if self.ElmitecUviewConnected:
            return True
        try:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.settimeout(self.Timeout)
            self.s.connect((self.IP, self.Port))
            self.s.send(b'asc')          # start string communication
            self.ElmitecUviewConnected = True     # TCPBlockingReceive needs it
            self.TCPBlockingReceive()
        except (ElmitecUviewError, OSError) as e:
            self.ElmitecUviewConnected = False
            try:
                self.s.close()
            except Exception:                                 # noqa: BLE001
                pass
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't connect to UView at %s:%d: %s"
                            % (self.IP, self.Port, e))
            self.debug_stream("Can't connect to UView: %s" % e)
            return False
        self.set_state(tango.DevState.ON)
        self.set_status("Connected to UView at %s:%d" % (self.IP, self.Port))
        self.debug_stream("Connected to UView")
        return True

    def disconnect(self):
        if self.ElmitecUviewConnected:
            try:
                self.s.send(b'clo')
                self.s.close()
            except OSError as e:
                self.debug_stream("Untidy disconnect: %s" % e)
            self.ElmitecUviewConnected = False
            self.debug_stream("Disconnected!")
    # PROTECTED REGION END #    //  ElmitecUview.class_variable

    # -----------------
    # Device Properties
    # -----------------

    IP = device_property(
        dtype='str', default_value="tvips.lab"
    )

    Port = device_property(
        dtype='uint', default_value=5570
    )

    Timeout = device_property(
        dtype='float', default_value=5.0,
        doc='Seconds to wait on the socket. Without one, a program that is '
            'alive but silent blocked a read for ever.',
    )

    ReconnectPeriod = device_property(
        dtype='float', default_value=10.0,
        doc='Seconds between attempts to rebuild the link while it is down.',
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
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
    )

    IntensityROI2 = attribute(
        dtype='double',
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
        self.set_change_event("IntensityROI2", True, False)
        # PROTECTED REGION ID(ElmitecUview.init_device) ENABLED START #
        # connect() reports FAULT and returns rather than raising, so a
        # UView that is not running no longer takes the server down.
        self.ElmitecUviewConnected = False
        self._reconnect = None
        self.connect()
        # And it keeps trying, so restarting UView does not mean
        # restarting this server as well.
        self._reconnect = _Reconnect(self)
        self._reconnect.start()
        # PROTECTED REGION END #    //  ElmitecUview.init_device
    def always_executed_hook(self):
        # PROTECTED REGION ID(ElmitecUview.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  ElmitecUview.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(ElmitecUview.delete_device) ENABLED START #
        if (getattr(self, "_reconnect", None) is not None):
            self._reconnect.stop.set()
        self.disconnect()
        self.set_state(tango.DevState.OFF)
        # PROTECTED REGION END #    //  ElmitecUview.delete_device
    def read_IntensityROI1(self):
        # PROTECTED REGION ID(ElmitecUview.IntensityROI1_read) ENABLED START #
        return self.getROIdata(1)
        # PROTECTED REGION END #    //  ElmitecUview.IntensityROI1_read

    def read_Exposure(self):
        # PROTECTED REGION ID(ElmitecUview.Exposure_read) ENABLED START #
        self._send(b"ext")
        data = self.TCPBlockingReceive()
        return float(data)
        # PROTECTED REGION END #    //  ElmitecUview.Exposure_read

    def write_Exposure(self, value):
        # PROTECTED REGION ID(ElmitecUview.Exposure_write) ENABLED START #
        self._send(("ext "+str(value)).encode("ascii"))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecUview.Exposure_write

    def read_Average(self):
        # PROTECTED REGION ID(ElmitecUview.Average_read) ENABLED START #
        self._send(b"avr")
        data = self.TCPBlockingReceive()
        return int(data)
        # PROTECTED REGION END #    //  ElmitecUview.Average_read

    def write_Average(self, value):
        # PROTECTED REGION ID(ElmitecUview.Average_write) ENABLED START #
        self._send(("avr "+str(value)).encode("ascii"))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecUview.Average_write

    def read_AcquisitionInProgress(self):
        # PROTECTED REGION ID(ElmitecUview.AcquisitionInProgress_read) ENABLED START #
        # Deprecated: this used to send "aip" too, so it and ContinousAcquisition
        # stepped on each other on the single UView socket. Read
        # ContinousAcquisition instead; this stub is kept only so existing
        # clients of the attribute do not break.
        return (True)
        # PROTECTED REGION END #    //  ElmitecUview.AcquisitionInProgress_read

    def read_ImageWidth(self):
        # PROTECTED REGION ID(ElmitecUview.ImageWidth_read) ENABLED START #
        self._send(b"giw")
        data = self.TCPBlockingReceive()
        return int(data)
        # PROTECTED REGION END #    //  ElmitecUview.ImageWidth_read

    def read_ImageHeight(self):
        # PROTECTED REGION ID(ElmitecUview.ImageHeight_read) ENABLED START #
        self._send(b"gih")
        data = self.TCPBlockingReceive()
        return int(data)
        # PROTECTED REGION END #    //  ElmitecUview.ImageHeight_read

    def read_Binning(self):
        # PROTECTED REGION ID(ElmitecUview.Binning_read) ENABLED START #
        self._send(b"bin")
        data = self.TCPBlockingReceive()
        return int(data.split()[0])
        # PROTECTED REGION END #    //  ElmitecUview.Binning_read

    def read_ContinousAcquisition(self):
        # PROTECTED REGION ID(ElmitecUview.ContinousAcquisition_read) ENABLED START #
        self._send(b"aip")
        data = self.TCPBlockingReceive()
        return int(data)
        # PROTECTED REGION END #    //  ElmitecUview.ContinousAcquisition_read

    def write_ContinousAcquisition(self, value):
        # PROTECTED REGION ID(ElmitecUview.ContinousAcquisition_write) ENABLED START #
        self._send(("aip "+str(int(value))).encode("ascii"))
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecUview.ContinousAcquisition_write

    def read_IntensityROI2(self):
        # PROTECTED REGION ID(ElmitecUview.IntensityROI2_read) ENABLED START #
        return self.getROIdata(2)
        # PROTECTED REGION END #    //  ElmitecUview.IntensityROI2_read

    def read_ImageData(self):
        # PROTECTED REGION ID(ElmitecUview.ImageData_read) ENABLED START #
        #self._send("ida 0 0 ")
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
        self._send(b"asi -1")
        data = self.TCPBlockingReceive()
        # PROTECTED REGION END #    //  ElmitecUview.AcquireSingleImage

    @command(
    dtype_in='str', 
    dtype_out='str', 
    )
    @DebugIt()
    def SaveImageAsDAT(self, argin):
        # PROTECTED REGION ID(ElmitecUview.SaveImageAsDAT) ENABLED START #
        self._send(("exp 0,0,"+argin).encode("ascii"))
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
        self._send(("exp 1,2,"+argin).encode("ascii"))
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
        self._send(argin.encode("ascii"))
        data = self.TCPBlockingReceive()
        return data
        # PROTECTED REGION END #    //  ElmitecUview.sendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(ElmitecUview.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((ElmitecUview,), args=args, **kwargs)
    # PROTECTED REGION END #    //  ElmitecUview.main

if __name__ == '__main__':
    main()
