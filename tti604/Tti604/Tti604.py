# -*- coding: utf-8 -*-
#
# This file is part of the Tti604 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" tti604

Device to use the RS TTI 604 DVMM. It has a rather horrible interface.
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
# PROTECTED REGION ID(Tti604.additionnal_import) ENABLED START
import serial
import time
# PROTECTED REGION END #    //  Tti604.additionnal_import

__all__ = ["Tti604", "main"]


class Tti604(Device):
    """
    Device to use the RS TTI 604 DVMM. It has a rather horrible interface.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(Tti604.class_variable) ENABLED START #
    def parse_output(self,resp):
        units=["None","mV","V","mA","A","Ohm","Continuity","Diode Test"]
        #rangeOhm=[400,4000,40000,400000,4000000,40000000]
        rangeOhm=["400 Ohm","4 kOhm","40 kOhm","400 kOhm","4 MOhm","40 MOhm"]
        acdc=["DC","AC"]
        rangeVAC=["0","4","40","400","750","0"]
        rangeVDC=["0","4","40","400","1000"]
        rangeVDC=["0","4","40","400","1000","0"]
        rangeIAC=["0","0.001","10","0.1","0","0"]
        rangeIDC=["0","0.004","10","0.4","0","0"]
        ranges={"mV":rangeVDC,"V":rangeVDC,"Ohm":rangeOhm,"mA":rangeIDC,"A":rangeIDC} # This is not exact, ranges are slighly different for DC and AC.
        funtionINFO=["THOLD","MINMAX","HERTZ","NULL","AUTO"]
        statusINFO=["DBEEP","AUTORANGE","CONTBUZZ","DISP MIN","DISP MAX","DISP HOLD","GATE10s"]
        numbercode = {252:'0',253:"0.", 96:'1',97:"1.", 218:'2',219:"2.", 242:'3',243:"3.", 102:'4',103:"4.", 182:'5',183:"5.", 190:'6',191:"6.", 224:'7',225:"7.",254:'8',255:"8.", 230:'9',231:"9.", 238:'A', 156:'C', 122:'D', 158:'E', 142:'F', 143:"F.", 140:'R', 30:'T', 124:'U', 28:'L', 29:'L.', 0: " ", 1: ".", 2: " " }
        try:
            result=("-" if resp[3]&0b10 else "+")+numbercode[resp[4]]+numbercode[resp[5]]+numbercode[resp[6]]+numbercode[resp[7]]+numbercode[resp[8]]
            if(result.replace(".","").find("FL")!=-1): # Output from out-of-range resistance reading is .0FL, 0.FL, 0F.L, etc.
                result="-9999"
            unit=units[resp[1]&0b111]
            output=(float(result),units[resp[1]&0b111],acdc[int(resp[1]&0b1000)//8],("AUTO" if resp[2]&0b1000000 else "")+("THOLD" if (resp[2]&0b1) else "")+("MINMAX" if (resp[2]&0b10) else "")+(("GATE" if resp[9]&0b10000000 else "")+("DOUBLEBP" if (resp[9]&0b1) else "")+("AUTORANGE" if (resp[2]&0b10) else "")+(" CONT BUZZ" if resp[9]&0b100 else "")+("DISP MIN" if resp[9]&0b1000 else "")+("DISP MAX" if resp[9]&0b100000 else "")+("DISP HOLD" if resp[9]&0b1000000 else "")),ranges[unit][int(resp[1]&0b1110000)//16])
        #print(rangeVDC[int(resp[1]&0b1110000)//16],end="");print(",",end="")
        
        except:
            raise ParseError
            return(("nada"))
        return(output)
    
    
    def command_tti(self,k):
        """ Result will be false in anycase if remote mode is on, because the response will be mixed with the data stream """
        self.ser.rts=False
        ka=bytes(k,"ascii")
        i=0
        while(i<5): # Try up to 5 times
            self.ser.flushInput()
            self.ser.write(ka)
            if (self.ser.read(1)==ka):
                return(True)
            i+=1
        self.set_state(PyTango.DevState.FAULT)
        return(False)
    
    def status_tti(self):
        self.ser.rts=False
        self.ser.flushInput()
        b=self.ser.in_waiting
        time.sleep(1)
        if (b!=self.ser.in_waiting):
            return("LOGGING")
        self.command_tti("u")
        resp=self.ser.read(10)
        self.command_tti("v")
        if (len(resp)!=10):
            return("OFF")
        return("ON")


    def read_tti(self):
        """ Problem: first batch of numbers after enable output is garbage. So need to read until numbers make sense. Use errors in parse_output as "sensor" """
        self.ser.rts=False
        self.ser.flushInput()
        self.command_tti("u")
        resp=self.ser.read(10)
        i=0
        while (i<10): # Try 10 times before giving up
            resp=self.ser.read(10)
            i+=1
            try:
                out=self.parse_output(resp)
            except:
                self.ser.flushInput()
            else:
                break
        self.command_tti("v")
        self.ser.flushInput()
        #print(i)
        if (i==10):
            return((0,"ERROR","ERROR","ERROR","ERROR"))
        return(out)

    def fast_read_tti(self):
        """ This assumes the DVV is already in remote mode"""
        self.ser.rts=False
        self.ser.flushInput()
        resp=self.ser.read(30)
        try:
            out=self.parse_output(bytes("\r","ascii")+resp.split(bytes("\r","ascii"))[1])
        except:
            return(0,"ERROR","ERROR","ERROR","ERROR")
        return(out)


    def testing_tti(self):
        self.command_tti("u")
        for i in range(10):
            resp=self.ser.read(10)
        self.command_tti("v")
        return(resp)
        
        # PROTECTED REGION END #    //  Tti604.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str', default_value="/dev/ttyUSB0"
    )

    # ----------
    # Attributes
    # ----------

    Mode = attribute(
        dtype='DevEnum',
        access=AttrWriteType.WRITE,
        memorized=True,
        hw_memorized=True,
        enum_labels=["Voltage", "Resistance", "Current10A", "CurrentmA", ],
    )

    ACDC = attribute(
        dtype='DevEnum',
        enum_labels=["AC", "DC", ],
    )

    Range = attribute(
        dtype='str',
    )

    Reading = attribute(
        dtype='double',
    )

    FunctionInfo = attribute(
        dtype='str',
        display_level=DispLevel.EXPERT,
    )

    Units = attribute(
        dtype='str',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(Tti604.init_device) ENABLED START #
        try:
            self.ser=serial.Serial(self.SerialPort,9600,dsrdtr=True,timeout=0.5)
        except IOError as Argument:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Can't connect to AMLPGC1")
            self.debug_stream("Can't connect to AMLPGC1")
        self.ser.rts=False
        self.set_status("Connected to AMLPGC1")
        self.debug_stream("Connected to AMLPGC1")
        if (self.status_tti()=="LOGGING"):
            self.set_state(PyTango.DevState.RUNNING)
        elif (self.status_tti()=="OFF"):
            self.set_state(PyTango.DevState.OFF)
        elif (self.status_tti()=="ON"):
            self.set_state(PyTango.DevState.ON)
            # PROTECTED REGION END #    //  Tti604.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(Tti604.always_executed_hook) ENABLED START #
            pass
            # PROTECTED REGION END #    //  Tti604.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(Tti604.delete_device) ENABLED START #
        if (self.get_state()==PyTango.DevState.RUNNING):
                self.command_tti("u") #turn off loggin mode
        self.ser.close()
        # PROTECTED REGION END #    //  Tti604.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def write_Mode(self, value):
        # PROTECTED REGION ID(Tti604.Mode_write) ENABLED START #
            if (value==0):
                self.command_tti("f") #Voltage
            elif (value==1):
                self.command_tti("i") #Resistance
            elif (value==2):
                self.command_tti("d") #Current 10A
            elif (value==3):
                self.command_tti("e") #Current mA
            # PROTECTED REGION END #    //  Tti604.Mode_write

    def read_ACDC(self):
        # PROTECTED REGION ID(Tti604.ACDC_read) ENABLED START #
            if (self.acdc=="AC"):
                return(0)
            elif (self.acdc=="DC"):
                return(1)
            return(0)
            # PROTECTED REGION END #    //  Tti604.ACDC_read

    def read_Range(self):
        # PROTECTED REGION ID(Tti604.Range_read) ENABLED START #
            return(self.vrange)
            # PROTECTED REGION END #    //  Tti604.Range_read

    def read_Reading(self):
        # PROTECTED REGION ID(Tti604.Reading_read) ENABLED START #
            state=self.get_state()
            if (state==PyTango.DevState.OFF):
                reading=(0.0,"None","None","None","None")
            elif (state==PyTango.DevState.ON):
                reading=self.read_tti()
            elif (state==PyTango.DevState.RUNNING):
                reading=self.fast_read_tti()
            self.value=reading[0]
            self.units=reading[1]
            self.vrange=reading[4]
            self.acdc=reading[2]
            self.functioninfo=reading[3]
            #self.functionstatus=reading[4]
            return (self.value)
            # PROTECTED REGION END #    //  Tti604.Reading_read

    def read_FunctionInfo(self):
        # PROTECTED REGION ID(Tti604.FunctionInfo_read) ENABLED START #
            return(self.functioninfo)
            # PROTECTED REGION END #    //  Tti604.FunctionInfo_read

    def read_Units(self):
        # PROTECTED REGION ID(Tti604.Units_read) ENABLED START #
        return(self.units)
        # PROTECTED REGION END #    //  Tti604.Units_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def On(self):
        # PROTECTED REGION ID(Tti604.On) ENABLED START #
        state=self.get_state()
        if (state==PyTango.DevState.OFF):
            self.command_tti("g")
        if (state==PyTango.DevState.RUNNING):
            self.command_tti("v")
        self.set_state(PyTango.DevState.ON)
            # PROTECTED REGION END #    //  Tti604.On

    @command(
    )
    @DebugIt()
    def Off(self):
        # PROTECTED REGION ID(Tti604.Off) ENABLED START #
        state=self.get_state()
        if (state==PyTango.DevState.ON):
            self.command_tti("g")
        if (state==PyTango.DevState.RUNNING):
            self.command_tti("v")
            self.command_tti("g")
        self.set_state(PyTango.DevState.OFF)
        # PROTECTED REGION END #    //  Tti604.Off

    @command(
    dtype_in='str', 
    dtype_out='bool', 
    display_level=DispLevel.EXPERT,
    )
    @DebugIt()
    def SendCommand(self, argin):
        # PROTECTED REGION ID(Tti604.SendCommand) ENABLED START #
        return(self.command_tti(argin))
        # PROTECTED REGION END #    //  Tti604.SendCommand

    @command(
    )
    @DebugIt()
    def AutoRange(self):
        # PROTECTED REGION ID(Tti604.AutoRange) ENABLED START #
        self.command_tti("c")
        # PROTECTED REGION END #    //  Tti604.AutoRange

    @command(
    )
    @DebugIt()
    def IncreaseRange(self):
        # PROTECTED REGION ID(Tti604.IncreaseRange) ENABLED START #
        self.command_tti("a")
        # PROTECTED REGION END #    //  Tti604.IncreaseRange

    @command(
    )
    @DebugIt()
    def DecreaseRange(self):
        # PROTECTED REGION ID(Tti604.DecreaseRange) ENABLED START #
        self.command_tti("b")
        # PROTECTED REGION END #    //  Tti604.DecreaseRange

    @command(
    )
    @DebugIt()
    def Run(self):
        # PROTECTED REGION ID(Tti604.Run) ENABLED START #
        state=self.get_state()
        if (state==PyTango.DevState.OFF):
            self.command_tti("g")
            self.command_tti("u")
        if (state==PyTango.DevState.ON):
            self.command_tti("u")
        self.set_state(PyTango.DevState.RUNNING)
        # PROTECTED REGION END #    //  Tti604.Run

    @command(
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(Tti604.Stop) ENABLED START #
        state=self.get_state()
        if (state==PyTango.DevState.OFF):
            self.command_tti("g")
        if (state==PyTango.DevState.RUNNING):
            self.command_tti("v")
        self.set_state(PyTango.DevEnum.ON)
        # PROTECTED REGION END #    //  Tti604.Stop

    @command(
    )
    @DebugIt()
    def setAC(self):
        # PROTECTED REGION ID(Tti604.setAC) ENABLED START #
        self.command_tti("l")
        # PROTECTED REGION END #    //  Tti604.setAC

    @command(
    )
    @DebugIt()
    def setDC(self):
        # PROTECTED REGION ID(Tti604.setDC) ENABLED START #
        self.command_tti("m")
        # PROTECTED REGION END #    //  Tti604.setDC

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(Tti604.main) ENABLED START #
    return run((Tti604,), args=args, **kwargs)
    # PROTECTED REGION END #    //  Tti604.main

if __name__ == '__main__':
    main()
