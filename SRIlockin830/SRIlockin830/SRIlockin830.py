# -*- coding: utf-8 -*-
#
# This file is part of the SRIlockin830 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" SRIlockin830

Interface to the SRI 830 Lock in.
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
# PROTECTED REGION ID(SRIlockin830.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  SRIlockin830.additionnal_import

__all__ = ["SRIlockin830", "main"]


class SRIlockin830(Device, metaclass=DeviceMeta):
    """
    Interface to the SRI 830 Lock in.
    """
    # PROTECTED REGION ID(SRIlockin830.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  SRIlockin830.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str', default_value="/dev/serial/by-path/platform-3f980000.usb-usb-0:1.3:1.0-port0"
    )

    Speed = device_property(
        dtype='int16', default_value=9600
    )

    # ----------
    # Attributes
    # ----------

    Phase = attribute(
        dtype='double',
        unit="grad",
    )

    Frequency = attribute(
        dtype='double',
    )

    X = attribute(
        dtype='double',
    )

    Y = attribute(
        dtype='double',
    )

    Mod = attribute(
        dtype='double',
    )

    TimeConstant = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
    )

    Sensitivity = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
    )

    Sync = attribute(
        dtype='bool',
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(SRIlockin830.init_device) ENABLED START #
        try:
            self.ser=serial.Serial(port=self.SerialPort,baudrate=self.Speed,bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,stopbits=1,timeout=0.5)
            self.ser.write(bytes("*IDN?\n","ascii"))
            identification=self.ser.read_until(bytes("\r","ascii"))
        except:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Can't connect to SRI 830")
            self.debug_stream("Can't connect to SRI 830")
            return
        if  (identification[0:31]!=bytes("Stanford_Research_Systems,SR830","ascii")):
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("I do not find an SRI 830 on the serial port")
            self.debug_stream("I do not find an SRI 830 on the serial port")
            return
        self.set_status("Connected to SRI 830")
        self.debug_stream("Connected to SRI 830")
        self.set_state(PyTango.DevState.ON)
        # PROTECTED REGION END #    //  SRIlockin830.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(SRIlockin830.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  SRIlockin830.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(SRIlockin830.delete_device) ENABLED START #
        self.ser.close()
        # PROTECTED REGION END #    //  SRIlockin830.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Phase(self):
        # PROTECTED REGION ID(SRIlockin830.Phase_read) ENABLED START #
        self.ser.write (bytes ("OUTP ? 4\n", "ascii"))
        resp=self.ser.read_until(bytes('\r',"ascii"))
        return float(resp)
        # PROTECTED REGION END #    //  SRIlockin830.Phase_read

    def read_Frequency(self):
        # PROTECTED REGION ID(SRIlockin830.Frequency_read) ENABLED START #
        self.ser.write (bytes ("FREQ ?\n", "ascii"))
        resp=self.ser.read_until(bytes('\r',"ascii"))
        return float(resp)
        # PROTECTED REGION END #    //  SRIlockin830.Frequency_read

    def read_X(self):
        # PROTECTED REGION ID(SRIlockin830.X_read) ENABLED START #
        self.ser.write (bytes ("OUTP ? 1\n", "ascii"))
        resp=self.ser.read_until(bytes('\r',"ascii"))
        return float(resp)
        # PROTECTED REGION END #    //  SRIlockin830.X_read

    def read_Y(self):
        # PROTECTED REGION ID(SRIlockin830.Y_read) ENABLED START #
        self.ser.write (bytes ("OUTP ? 2\n", "ascii"))
        resp=self.ser.read_until(bytes('\r',"ascii"))
        return float(resp)
        # PROTECTED REGION END #    //  SRIlockin830.Y_read

    def read_Mod(self):
        # PROTECTED REGION ID(SRIlockin830.Mod_read) ENABLED START #
        self.ser.write (bytes ("OUTP ? 3\n", "ascii"))
        resp=self.ser.read_until(bytes('\r',"ascii"))
        return float(resp)
        # PROTECTED REGION END #    //  SRIlockin830.Mod_read

    def read_TimeConstant(self):
        # PROTECTED REGION ID(SRIlockin830.TimeConstant_read) ENABLED START #
        self.ser.write (bytes ("OFLT ?\n", "ascii"))
        resp=self.ser.read_until(bytes('\r',"ascii"))
        return int(resp)
        # PROTECTED REGION END #    //  SRIlockin830.TimeConstant_read

    def write_TimeConstant(self, value):
        # PROTECTED REGION ID(SRIlockin830.TimeConstant_write) ENABLED START #
        self.ser.write (bytes ("OFLT %d\n"%value, "ascii"))
        # PROTECTED REGION END #    //  SRIlockin830.TimeConstant_write

    def read_Sensitivity(self):
        # PROTECTED REGION ID(SRIlockin830.Sensitivity_read) ENABLED START #
        self.ser.write (bytes ("SENS ?\n", "ascii"))
        resp=self.ser.read_until(bytes('\r',"ascii"))
        return int(resp)
        # PROTECTED REGION END #    //  SRIlockin830.Sensitivity_read

    def write_Sensitivity(self, value):
        # PROTECTED REGION ID(SRIlockin830.Sensitivity_write) ENABLED START #
        self.ser.write (bytes ("SENS %d\n"%value, "ascii"))
        # PROTECTED REGION END #    //  SRIlockin830.Sensitivity_write

    def read_Sync(self):
        # PROTECTED REGION ID(SRIlockin830.Sync_read) ENABLED START #
        self.ser.write (bytes ("SYNC ?\n", "ascii"))
        resp=self.ser.read_until(bytes('\r',"ascii"))
        return (int(resp)==1)
        # PROTECTED REGION END #    //  SRIlockin830.Sync_read

    def write_Sync(self, value):
        # PROTECTED REGION ID(SRIlockin830.Sync_write) ENABLED START #
        if (value==True):
            self.ser.write (bytes ("SYNC 1\n", "ascii"))
        else:
            self.ser.write (bytes ("SYNC 0\n", "ascii"))
        # PROTECTED REGION END #    //  SRIlockin830.Sync_write


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def AutoPhase(self):
        # PROTECTED REGION ID(SRIlockin830.AutoPhase) ENABLED START #
        self.ser.write (bytes ("APHS\n", "ascii"))
        # PROTECTED REGION END #    //  SRIlockin830.AutoPhase

    @command(
    )
    @DebugIt()
    def AutoGain(self):
        # PROTECTED REGION ID(SRIlockin830.AutoGain) ENABLED START #
        self.ser.write (bytes ("AGAN\n", "ascii"))
        busy=1
        while(busy):
            self.ser.write (bytes ("*STB? 1\n", "ascii"))
            resp=self.ser.read_until(bytes('\r',"ascii"))
            busy=int(resp)
        # PROTECTED REGION END #    //  SRIlockin830.AutoGain

    @command(
    dtype_in='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def SendCmd(self, argin):
        # PROTECTED REGION ID(SRIlockin830.SendCmd) ENABLED START #
        self.ser.write (bytes (argin+"\n", "ascii"))
        return ""
        # PROTECTED REGION END #    //  SRIlockin830.SendCmd

    @command(
    dtype_in='str', 
    dtype_out='str', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def SndCmdResponse(self, argin):
        # PROTECTED REGION ID(SRIlockin830.SndCmdResponse) ENABLED START #
        self.ser.write (bytes (argin+"\n", "ascii"))
        resp=self.ser.read_until(bytes('\r',"ascii"))
        return resp
        # PROTECTED REGION END #    //  SRIlockin830.SndCmdResponse

    @command(
    )
    @DebugIt()
    def AutoReserve(self):
        # PROTECTED REGION ID(SRIlockin830.AutoReserve) ENABLED START #
        self.ser.write (bytes ("ARSV\n", "ascii"))
        busy=1
        while(busy):
            self.ser.write (bytes ("*STB? 1\n", "ascii"))
            resp=self.ser.read_until(bytes('\r',"ascii"))
            busy=int(resp)
        # PROTECTED REGION END #    //  SRIlockin830.AutoReserve

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(SRIlockin830.main) ENABLED START #
    return run((SRIlockin830,), args=args, **kwargs)
    # PROTECTED REGION END #    //  SRIlockin830.main

if __name__ == '__main__':
    main()
