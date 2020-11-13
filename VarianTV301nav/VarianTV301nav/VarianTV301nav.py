# -*- coding: utf-8 -*-
#
# This file is part of the VarianTV301nav project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" Varian TV301NAV

Driver for interfacing with the Varian/Agilent TV301 Navigator pump with integrated controller.
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
# PROTECTED REGION ID(VarianTV301nav.additionnal_import) ENABLED START #
import serial
# PROTECTED REGION END #    //  VarianTV301nav.additionnal_import

__all__ = ["VarianTV301nav", "main"]


class VarianTV301nav(Device):
    """
    Driver for interfacing with the Varian/Agilent TV301 Navigator pump with integrated controller.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(VarianTV301nav.class_variable) ENABLED START #
    
    status_code=["Stop","WaitinIntlk","Starting","Auto-tunning","Braking","Normal","Fail"]
    
    def sendcommand(self,win,data):
        cmd='\x02'+'\x80'+win+'\x31'+data+'\x03'
        full_cmd=cmd+self.crc_code(cmd)
        self.ser.write(full_cmd)
        return(ord(self.ser.read(6)[2:3]))

    def readcommand(self,win,nb):
        cmd='\x02'+'\x80'+win+'\x30'+'\x03'
        full_cmd=cmd+self.crc_code(cmd)
        self.ser.write(full_cmd)
        return(self.ser.read(nb))
   
    def crc_code(self,a):
        result=0
        for i in range(1,len(a)):
            result = result ^ ord(a[i])
        return('{:02x}'.format(result))
        
    def setRemoteMode(self):
	self.sendcommand("008","1") # Controller left in remote mode, not serial. It is the default mode after removing power. It is a read-only mode for all the settings.

    def setSerialMode(self):
	self.sendcommand("008","0") # Serial mode, full control.

    # PROTECTED REGION END #    //  VarianTV301nav.class_variable

    # -----------------
    # Device Properties
    # -----------------

    serialPort = device_property(
        dtype='str',
        mandatory=True
    )

    # ----------
    # Attributes
    # ----------

    setSpeed = attribute(
        dtype='uint16',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        label="Set Speed",
        unit="Hz",
        standard_unit="Hz",
        display_unit="Hz",
        max_value=950,
        min_value=0,
    )

    temperature = attribute(
        dtype='uint16',
        label="temperature",
        unit="ºC",
        standard_unit="ºC",
        display_unit="ºC",
        max_value=50,
        min_value=0,
    )

    power = attribute(
        dtype='uint16',
        label="power",
        unit="W",
        standard_unit="W",
        display_unit="W",
        max_value=150,
        min_value=0,
    )

    turboStatus = attribute(
        dtype='str',
        label="status",
    )

    running = attribute(
        dtype='bool',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        label="Running",
    )

    valveOperation = attribute(
        dtype='bool',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        label="valveOperation",
        unit="(false=automatic)",
    )

    ventValve = attribute(
        dtype='bool',
        access=AttrWriteType.READ_WRITE,
        display_level=DispLevel.EXPERT,
        label="ventValve",
        unit="(1=closed)",
    )

    errorCode = attribute(
        dtype='uint16',
        display_level=DispLevel.EXPERT,
        label="errorCode",
    )

    current = attribute(
        dtype='uint16',
        label="current",
        unit="mA",
        standard_unit="mA",
        display_unit="mA",
        format="%d",
    )

    voltage = attribute(
        dtype='uint16',
        label="voltage",
        unit="V",
        standard_unit="V",
        display_unit="V",
        format="%d",
    )

    frecuency = attribute(
        dtype='uint16',
        label="frequency",
        unit="Hz",
        standard_unit="Hz",
        display_unit="Hz",
        max_value=963,
        min_value=0,
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(VarianTV301nav.init_device) ENABLED START #
        self.ser=serial.Serial(self.serialPort,baudrate=9600,bytesize=8,parity="N",stopbits=1,timeout=0.5)
	if (self.read_running()==True):
		self.setSerialMode() # Set comunicacion mode, not "remote"
		self.sendcommand("000","1")
		self.set_state(PyTango.DevState.ON)
		self.set_status("VarianTV301 connected and running")
	else:
		self.setSerialMode() # Set serial comunicacion mode, not "remote"
		self.sendcommand("000","0")
		self.set_state(PyTango.DevState.OFF)
		self.set_status("VarianTV301 connected")
        # PROTECTED REGION END #    //  VarianTV301nav.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(VarianTV301nav.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  VarianTV301nav.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(VarianTV301nav.delete_device) ENABLED START #
	    self.setRemoteMode() 
	    # Set "Remote" read-only mode. Just in case.
            self.ser.close()
        # PROTECTED REGION END #    //  VarianTV301nav.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_setSpeed(self):
        # PROTECTED REGION ID(VarianTV301nav.setSpeed_read) ENABLED START #
        response=self.readcommand("120",15)
        return(int(response[6:12]))
        # PROTECTED REGION END #    //  VarianTV301nav.setSpeed_read

    def write_setSpeed(self, value):
        # PROTECTED REGION ID(VarianTV301nav.setSpeed_write) ENABLED START #
        if value>150:
            speed_str="%06d"%value
            res=self.sendcommand("120",speed_str)
            if (res==21):
                self.set_status("SetSpeed not done")
                self.debug_stream("SetSpeed not done")
            elif (res==6):
                print("OK")
            else:
                print(res)
        # PROTECTED REGION END #    //  VarianTV301nav.setSpeed_write

    def read_temperature(self):
        # PROTECTED REGION ID(VarianTV301nav.temperature_read) ENABLED START #
        response=self.readcommand("204",15)
        return(int(response[6:12]))
        # PROTECTED REGION END #    //  VarianTV301nav.temperature_read

    def read_power(self):
        # PROTECTED REGION ID(VarianTV301nav.power_read) ENABLED START #
        response=self.readcommand("202",15)
        return(int(response[6:12]))
        # PROTECTED REGION END #    //  VarianTV301nav.power_read

    def read_turboStatus(self):
        # PROTECTED REGION ID(VarianTV301nav.turboStatus_read) ENABLED START #
 	response=self.readcommand("205",15)
        return(self.status_code[int(response[6:12])])
        # PROTECTED REGION END #    //  VarianTV301nav.turboStatus_read

    def read_running(self):
        # PROTECTED REGION ID(VarianTV301nav.running_read) ENABLED START #
	response=int(self.readcommand("000",10)[6:7])
        if (response==0):
 		return False
        else:
		return True
	return False # Default
        # PROTECTED REGION END #    //  VarianTV301nav.running_read

    def write_running(self, value):
        # PROTECTED REGION ID(VarianTV301nav.running_write) ENABLED START #
        if (value==True):
 		res=self.sendcommand("000","1")
        else:
		res=self.sendcommand("000","0")
	pass
        # PROTECTED REGION END #    //  VarianTV301nav.running_write

    def read_valveOperation(self):
        # PROTECTED REGION ID(VarianTV301nav.valveOperation_read) ENABLED START #
	response=int(self.readcommand("125",10)[6:7])
        if (response==0):
	        return False
	elif (response==1):
		return True
	return False # Default
        # PROTECTED REGION END #    //  VarianTV301nav.valveOperation_read

    def write_valveOperation(self, value):
        # PROTECTED REGION ID(VarianTV301nav.valveOperation_write) ENABLED START #
        if (value==True):
 		res=self.sendcommand("125","1")
        else:
		res=self.sendcommand("125","0")
	pass

        # PROTECTED REGION END #    //  VarianTV301nav.valveOperation_write

    def read_ventValve(self):
        # PROTECTED REGION ID(VarianTV301nav.ventValve_read) ENABLED START #
        response=int(self.readcommand("122",10)[6:7])
        if (response==0):
	        return False
	elif (response==1):
		return True
	return True # Default True, closed
        # PROTECTED REGION END #    //  VarianTV301nav.ventValve_read

    def write_ventValve(self, value):
        # PROTECTED REGION ID(VarianTV301nav.ventValve_write) ENABLED START #
       	if (value==True):
 		res=self.sendcommand("122","1")
        else:
		res=self.sendcommand("122","0")
	pass
        # PROTECTED REGION END #    //  VarianTV301nav.ventValve_write

    def read_errorCode(self):
        # PROTECTED REGION ID(VarianTV301nav.errorCode_read) ENABLED START #
        response=self.readcommand("125",10)
        return(int(response[6:7]))
        # PROTECTED REGION END #    //  VarianTV301nav.errorCode_read

    def read_current(self):
        # PROTECTED REGION ID(VarianTV301nav.current_read) ENABLED START #
	response=self.readcommand("200",15)
        return(int(response[6:12]))
        # PROTECTED REGION END #    //  VarianTV301nav.current_read

    def read_voltage(self):
        # PROTECTED REGION ID(VarianTV301nav.voltage_read) ENABLED START #
        response=self.readcommand("201",15)
        return(int(response[6:12]))
        # PROTECTED REGION END #    //  VarianTV301nav.voltage_read

    def read_frecuency(self):
        # PROTECTED REGION ID(VarianTV301nav.frecuency_read) ENABLED START #
	response=self.readcommand("203",15)
        return(int(response[6:12]))
        # PROTECTED REGION END #    //  VarianTV301nav.frecuency_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def Start(self):
        # PROTECTED REGION ID(VarianTV301nav.Start) ENABLED START #
	self.sendcommand("000","1")
	self.set_state(PyTango.DevState.ON)
        pass
        # PROTECTED REGION END #    //  VarianTV301nav.Start

    @command(
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(VarianTV301nav.Stop) ENABLED START #
        pass
	self.sendcommand("000","0")
	self.set_state(PyTango.DevState.OFF)
	pass
        # PROTECTED REGION END #    //  VarianTV301nav.Stop

    @command(
    dtype_in='uint16', 
    dtype_out='bool', 
    )
    @DebugIt()
    def SetSpeed(self, argin):
        # PROTECTED REGION ID(VarianTV301nav.SetSpeed) ENABLED START #
	if (argin>950):
		argin=950
	elif (argin<150):
		argin=150
	speed_str="%06d"%argin
        res=self.sendcommand("120",speed_str)
        if (res==21):
            return(False)
        elif (res==6):
            return(True)
        else:
            return(False)
        # PROTECTED REGION END #    //  VarianTV301nav.SetSpeed

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(VarianTV301nav.main) ENABLED START #
    return run((VarianTV301nav,), args=args, **kwargs)
    # PROTECTED REGION END #    //  VarianTV301nav.main

if __name__ == '__main__':
    main()
