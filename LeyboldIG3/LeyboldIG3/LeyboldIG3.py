# -*- coding: utf-8 -*-
#
# This file is part of the LeyboldIG3 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" LeyboldIG3

Server to use remotely the Leybold IG3 Gauge Electronics.
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
# PROTECTED REGION ID(LeyboldIG3.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  LeyboldIG3.additionnal_import

__all__ = ["LeyboldIG3", "main"]


class LeyboldIG3(Device,metaclass=DeviceMeta):
    """
    Server to use remotely the Leybold IG3 Gauge Electronics.
    """
    # PROTECTED REGION ID(LeyboldIG3.class_variable) ENABLED START #
    def cmd(self,a):
        b=bytes(a,"ascii")
        self.ser.write(bytes([2,len(b)])+b+bytes([sum(b)%256]))
    def response(self):
        h=self.ser.read(2)
        d=self.ser.read(h[1])
        ck=int.from_bytes(self.ser.read(1),byteorder="big")
        cck=sum(d)%256
        if (cck!=ck):
            return("CHK",d[1:])
        elif (d[0]==0x06):
            return(("ACK",d[1:]))
        elif (d[0]==0x15):
            return(("NAK",d[1:]))
    # PROTECTED REGION END #    //  LeyboldIG3.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str', default_value="/dev/ttyUSB0"
    )

    Speed = device_property(
        dtype='uint16', default_value=9600
    )

    # ----------
    # Attributes
    # ----------

    Pressure = attribute(
        dtype='double',
        label="Pressure",
        unit="mbar",
        format="%.1e",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(LeyboldIG3.init_device) ENABLED START #
        try:
            self.ser=serial.Serial(self.SerialPort,baudrate=self.Speed,timeout=1.0)
            self.cmd("H")
            r=self.response()
            if (r[0]=="NAK"):
                self.set_state(PyTango.DevState.FAULT)
                self.set_status("IG3 is saying it does not understand me")
                self.debug_stream("IG3 is saying it does not understand me")
                return
            elif (r[0]=="CHK"):
                self.set_state(PyTango.DevState.FAULT)
                self.set_status("IG3 is having checksum errors")
                self.debug_stream("IG3 is having checksum errors")
                return
            elif (str(r[1][0:3],"ascii")!="IG3"):
                self.set_state(PyTango.DevState.FAULT)
                self.set_status("This is not an IG3")
                self.debug_stream("This is not an IG3")
                return
        except serial.SerialTimeoutException:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Can't connect to IG3")
            self.debug_stream("Can't connect to IG3")
            return
        self.set_status("Connected to Leybold IG3")
        self.debug_stream("Connected to Leybold IG3")
        self.cmd("S14")
        r=self.response()
        if (str(r[1],"ascii")=="1"):
            self.set_state(PyTango.DevState.ON)
        else:
            self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  LeyboldIG3.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(LeyboldIG3.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  LeyboldIG3.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(LeyboldIG3.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  LeyboldIG3.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Pressure(self):
        # PROTECTED REGION ID(LeyboldIG3.Pressure_read) ENABLED START #
        state=self.get_state()
        if (state==PyTango.DevState.OFF):
            return 0.0
        self.cmd("S00")
        r=self.response()

        if (r[0]=="ACK"):
            return float(r[1])
        else:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status(r[0]+r[1])
            self.debug_stream(r[0]+r[1])
            return(0.0)
        # PROTECTED REGION END #    //  LeyboldIG3.Pressure_read


    # --------
    # Commands
    # --------

    @command(
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def Start(self):
        # PROTECTED REGION ID(LeyboldIG3.Start) ENABLED START #
        state=self.get_state()
        if (state==PyTango.DevState.ON):
            return
        elif (state==PyTango.DevState.OFF):
            self.cmd("R09")
            r=self.response()
            if (r[0]=="ACK"):
                self.set_state(PyTango.DevState.ON)
            else:
                self.set_status(r[0]+" "+str(r[1],"ascii"))
                self.debug_stream(r[0]+" "+str(r[1],"ascii"))
                self.set_state(PyTango.DevState.FAULT)
        # PROTECTED REGION END #    //  LeyboldIG3.Start

    @command(
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(LeyboldIG3.Stop) ENABLED START #
        state=self.get_state()
        if (state==PyTango.DevState.OFF):
            return
        else:
            self.cmd("R10")
            r=self.response()
            if (r[0]=="ACK"):
                self.set_state(PyTango.DevState.OFF)
            else:
                self.set_status(r[0]+" "+str(r[1],"ascii"))
                self.debug_stream(r[0]+" "+str(r[1],"ascii"))
                self.set_state(PyTango.DevState.FAULT)
        # PROTECTED REGION END #    //  LeyboldIG3.Stop

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def SendCommand(self, argin):
        # PROTECTED REGION ID(LeyboldIG3.SendCommand) ENABLED START #
        self.cmd(argin)
        r=self.response()
        return r[0]+" "+str(r[1],"ascii")
        # PROTECTED REGION END #    //  LeyboldIG3.SendCommand

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(LeyboldIG3.main) ENABLED START #
    return run((LeyboldIG3,), args=args, **kwargs)
    # PROTECTED REGION END #    //  LeyboldIG3.main

if __name__ == '__main__':
    main()
