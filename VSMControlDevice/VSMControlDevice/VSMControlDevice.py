# -*- coding: utf-8 -*-
#
# This file is part of the VSMControlDevice project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" VSM Control Device

Reading data and generation of images in hysteresis cycles
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
# PROTECTED REGION ID(VSMControlDevice.additionnal_import) ENABLED START #
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import time
import os
from datetime import datetime
import threading
import scipy

# PROTECTED REGION END #    //  VSMControlDevice.additionnal_import

__all__ = ["VSMControlDevice", "main"]


class VSMControlDevice(Device, metaclass=DeviceMeta):
    """
    Reading data and generation of images in hysteresis cycles
    """
    # PROTECTED REGION ID(VSMControlDevice.class_variable) ENABLED START #
        

    def save_cicle(self,complete = True):
        data = self.data
        filename = self.Filename.get_write_value()
        comment = self.Comment.get_write_value()
        path = self.path.get_write_value()
        if path[-1] == "/":
            None
        else:
            path += "/"

        day_folder = time.strftime("%Y-%m-%d")
        try:
            os.makedirs(path + day_folder)
        except OSError: None
        

        plt.clf()
        if complete:
            plt.plot(data[:int(len(data)/2),1],data[:int(len(data)/2),2],color="b",marker=".")
            plt.plot(data[int(len(data)/2):,1],data[int(len(data)/2):,2],color="r",marker=".")
        else: 
            plt.plot(data[:self.loop_index-1,2],color="b",marker=".")
        plt.title(filename+" "+comment)
        plt.xlabel("Magnetic Field (T)")
        plt.ylabel("Magnetization (arb. units)")
        
        
        scipy.savetxt(path + day_folder +"/"+ filename,data,header=comment)
        plt.savefig(path + day_folder +"/"+ filename+".png")
        plt.savefig(path + day_folder +"/"+ filename+".pdf")






    def histeresis_part(self,rang,delta_current,delta_t,polarice):
        for i in range(rang[0],rang[1],rang[2]):

            while self.do_stop:
                self.set_status("Stopped cycle")
                time.sleep(2)

            if self.do_cancel:
                self.set_status("Canceled")
                break


            #print("vuelta pos %d"%i)
            current=i*delta_current
            self.coilcurrent.Output=current
            time.sleep(delta_t)
            #mu=DVMlockin.Reading
            mu=self.lockin.X
            muy=self.lockin.Y
            mumod=self.lockin.Mod
            muang=self.lockin.Phase
            b=self.DVMsondaHall.Reading * (100/9.5379)
            self.data[self.loop_index,0]= polarice*current
            self.data[self.loop_index,1]=b
            self.data[self.loop_index,2]=mu
            self.data[self.loop_index,3]=muy
            self.data[self.loop_index,4]=mumod
            self.data[self.loop_index,5]=muang
            #plt.scatter(current,mu,color="b",marker=".")
            #plt.pause(0.05)
            self.loop_index+=1

    def Histeresis_Cicle(self):

        delta_current = self.Delta_Current.get_write_value() #Evitar cambios durante el ciclo
        delta_t = self.Delta_Time.get_write_value()

        n=int(self.Max_Current.get_write_value()/delta_current)
        self.n = n
        self.data=np.zeros((4*n,6),float)
        
        #Start Cicle
        self.loop_index = 0
        self.histeresis_part((n,0,-1),delta_current, delta_t, 1)
        if self.do_cancel: return None
        #Segunda
        self.coilcurrent.Output=0.0
        self.polarity.setNegative()
        self.polarity.Init()
        time.sleep(5) 
        self.histeresis_part((0,n,1),delta_current, delta_t, -1)
        if self.do_cancel: return None

        #Tercera 
        self.histeresis_part((n,0,-1),delta_current, delta_t, -1)
        if self.do_cancel: return None

        #Cuarta 
        self.coilcurrent.Output=0.0
        #polarity.Init()
        for i in range(4):
            self.polarity.setPositive()
            time.sleep(5)

        self.histeresis_part((0,n,1),delta_current, delta_t, 1)
        if self.do_cancel: return None

        self.save_cicle()
        # return_to_zero
        if (self.return_to_zero_end.get_write_value()):
            self.set_status("Cycle finished and saved, returning to zero")
            for i in range (n,0,-1):
                #print("vuelta pos %d"%i)
                current=i*delta_current
                self.coilcurrent.Output=current
                time.sleep(2)

        self.set_state(PyTango.DevState.ON)
        self.set_status("Cycle finished and saved")






    # PROTECTED REGION END #    //  VSMControlDevice.class_variable

    # -----------------
    # Device Properties
    # -----------------

    device_lockin = device_property(
        dtype='str',
        mandatory=True
    )

    device_DVMsondaHall = device_property(
        dtype='str',
        mandatory=True
    )

    device_coilcurrent = device_property(
        dtype='str',
        mandatory=True
    )

    device_polarity = device_property(
        dtype='str',
        mandatory=True
    )

    # ----------
    # Attributes
    # ----------

    Max_Current = attribute(
        dtype='double',
        access=AttrWriteType.WRITE,
        unit="Amper",
        display_unit="A",
        memorized=True,
        hw_memorized=True,
    )

    Delta_Current = attribute(
        dtype='double',
        access=AttrWriteType.WRITE,
        unit="Amper",
        display_unit="A",
        memorized=True,
        hw_memorized=True,
    )

    Delta_Time = attribute(
        dtype='double',
        access=AttrWriteType.WRITE,
        unit="Seconds",
        display_unit="s",
        memorized=True,
        hw_memorized=True,
    )

    Filename = attribute(
        dtype='str',
        access=AttrWriteType.WRITE,
        memorized=True,
        hw_memorized=True,
    )

    Comment = attribute(
        dtype='str',
        access=AttrWriteType.WRITE,
        memorized=True,
        hw_memorized=True,
    )

    return_to_zero_end = attribute(
        dtype='bool',
        access=AttrWriteType.WRITE,
        memorized=True,
        hw_memorized=True,
    )

    loking_TimeConstant = attribute(
        dtype='int16',
        access=AttrWriteType.READ_WRITE,
    )

    path = attribute(
        dtype='str',
        access=AttrWriteType.WRITE,
        memorized=True,
    )

    HysteresisCycles_Img = attribute(
        dtype=(('double',),),
        max_dim_x=720, max_dim_y=720,
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(VSMControlDevice.init_device) ENABLED START #

        try:
            #self.DVMlockin      = PyTango.DeviceProxy(self.device_DVMlockin)
            self.lockin         = PyTango.DeviceProxy(self.device_lockin)
            self.DVMsondaHall   = PyTango.DeviceProxy(self.device_DVMsondaHall)
            self.coilcurrent    = PyTango.DeviceProxy(self.device_coilcurrent)
            self.polarity       = PyTango.DeviceProxy(self.device_polarity)
        except:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("Not able to connect to input devices ({}, {}, {}, {}, {})".format(self.device_DVMlockin,
                                                                                               self.device_lockin,
                                                                                               self.device_DVMsondaHall,
                                                                                               self.device_coilcurrent,
                                                                                               self.device_polarity))
        
        else: 
            self.set_state(PyTango.DevState.ON)


        if True:
            #Para controlar los ciclos
            self.do_stop = False
            self.do_cancel = False
    

                




        # PROTECTED REGION END #    //  VSMControlDevice.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(VSMControlDevice.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  VSMControlDevice.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(VSMControlDevice.delete_device) ENABLED START #
        pass
        # PROTECTED REGION END #    //  VSMControlDevice.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def write_Max_Current(self, value):
        # PROTECTED REGION ID(VSMControlDevice.Max_Current_write) ENABLED START #
        pass
        # PROTECTED REGION END #    //  VSMControlDevice.Max_Current_write

    def write_Delta_Current(self, value):
        # PROTECTED REGION ID(VSMControlDevice.Delta_Current_write) ENABLED START #
        pass
        # PROTECTED REGION END #    //  VSMControlDevice.Delta_Current_write

    def write_Delta_Time(self, value):
        # PROTECTED REGION ID(VSMControlDevice.Delta_Time_write) ENABLED START #
        pass
        # PROTECTED REGION END #    //  VSMControlDevice.Delta_Time_write

    def write_Filename(self, value):
        # PROTECTED REGION ID(VSMControlDevice.Filename_write) ENABLED START #
        pass
        # PROTECTED REGION END #    //  VSMControlDevice.Filename_write

    def write_Comment(self, value):
        # PROTECTED REGION ID(VSMControlDevice.Comment_write) ENABLED START #
        pass
        # PROTECTED REGION END #    //  VSMControlDevice.Comment_write

    def write_return_to_zero_end(self, value):
        # PROTECTED REGION ID(VSMControlDevice.return_to_zero_end_write) ENABLED START #
        pass
        # PROTECTED REGION END #    //  VSMControlDevice.return_to_zero_end_write

    def read_loking_TimeConstant(self):
        # PROTECTED REGION ID(VSMControlDevice.loking_TimeConstant_read) ENABLED START # 
        return self.lockin.TimeConstant
        # PROTECTED REGION END #    //  VSMControlDevice.loking_TimeConstant_read

    def write_loking_TimeConstant(self, value):
        # PROTECTED REGION ID(VSMControlDevice.loking_TimeConstant_write) ENABLED START #
        self.lockin.TimeConstant = value 
        # PROTECTED REGION END #    //  VSMControlDevice.loking_TimeConstant_write

    def write_path(self, value):
        # PROTECTED REGION ID(VSMControlDevice.path_write) ENABLED START #
        pass
        # PROTECTED REGION END #    //  VSMControlDevice.path_write

    def read_HysteresisCycles_Img(self):
        # PROTECTED REGION ID(VSMControlDevice.HysteresisCycles_Img_read) ENABLED START #
        fig = Figure()
        canvas = FigureCanvas(fig)
        ax = fig.gca()

        ##### Dibujado
        #data = np.zeros((3,3),float)
        #data[:,1] = [5.0,5.5,7.0]
        #data[:,2] = [1.0,4.0,8.0] 
        data = self.data
        ax.plot(data[:self.loop_index-1,1],data[:self.loop_index-1,2],color="black",marker="o")
        ax.set_title(self.Filename.get_write_value()+" "+self.Comment.get_write_value())
        ax.set_xlabel("Magnetic Field (T)")
        ax.set_ylabel("Magnetization (arb. units)")
        #####

        fig.tight_layout(pad=0)
        #ax.margins(0)

        fig.canvas.draw()
        image_from_plot = np.frombuffer(fig.canvas.tostring_rgb(), dtype=np.uint8)
        image_from_plot = image_from_plot.reshape(fig.canvas.get_width_height()[::-1] + (3,))
        #for i in range(len(image_from_plot)):
        red = image_from_plot[:,:,0];
        green = image_from_plot[:,:,1];
        blue = image_from_plot[:,:,2];
        gray = (0.2989 * red + 0.5870 * green + 0.1140 * blue)/255
        return np.array(gray)     
        

        
        
        
        
        
        
        
        return 
        # PROTECTED REGION END #    //  VSMControlDevice.HysteresisCycles_Img_read


    # --------
    # Commands
    # --------

    @command(
    )
    @DebugIt()
    def Start(self):
        # PROTECTED REGION ID(VSMControlDevice.Start) ENABLED START #
        
        self.do_cancel = False
        self.do_stop = False
        histeresis_thread = threading.Thread(target=self.Histeresis_Cicle)
        histeresis_thread.start()

        time.sleep(1)
        self.set_state(PyTango.DevState.RUNNING)
        self.set_status("Empezando Ciclo con:\n\tFilename: {}\n\tComment: {}\nParametros:\n\tMax Current: {}\n\tA Steps: {}\n\tDelta Time: {}".format(self.Filename.get_write_value(),self.Comment.get_write_value(),self.Max_Current.get_write_value(),self.n,self.Delta_Time.get_write_value()))


        # PROTECTED REGION END #    //  VSMControlDevice.Start

    @command(
    )
    @DebugIt()
    def Stop(self):
        # PROTECTED REGION ID(VSMControlDevice.Stop) ENABLED START #
        self.do_stop = True
        self.set_state(PyTango.DevState.STANDBY)
        # PROTECTED REGION END #    //  VSMControlDevice.Stop

    @command(
    )
    @DebugIt()
    def Continue(self):
        # PROTECTED REGION ID(VSMControlDevice.Continue) ENABLED START #
        self.do_stop = False
        self.set_state(PyTango.DevState.RUNNING)
        self.set_status("Continuando Ciclo con:\n\tFilename: {}\n\tComment: {}\nParametros:\n\tMax Current: {}\n\tA Steps: {}\n\tDelta Time: {}".format(self.Filename.get_write_value(),self.Comment.get_write_value(),self.Max_Current.get_write_value(),self.n,self.Delta_Time.get_write_value()))

        # PROTECTED REGION END #    //  VSMControlDevice.Continue

    @command(
    )
    @DebugIt()
    def Cancel(self):
        # PROTECTED REGION ID(VSMControlDevice.Cancel) ENABLED START #

        self.do_cancel = True
        self.do_stop = False 
        ## Comprobar si realmente se ha cerrado el hilo antes de cambiar el estado 
        #TODO
        self.set_state(PyTango.DevState.ON) 

        # PROTECTED REGION END #    //  VSMControlDevice.Cancel

    @command(
    )
    @DebugIt()
    def Save_Actual(self):
        # PROTECTED REGION ID(VSMControlDevice.Save_Actual) ENABLED START #
        self.save_cicle(complete= False)
        # PROTECTED REGION END #    //  VSMControlDevice.Save_Actual

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(VSMControlDevice.main) ENABLED START #
    return run((VSMControlDevice,), args=args, **kwargs)
    # PROTECTED REGION END #    //  VSMControlDevice.main

if __name__ == '__main__':
    main()
