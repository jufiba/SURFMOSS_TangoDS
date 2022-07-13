#!/usr/bin/python
# LEEM Madrid Macros
# Simple acquisition using tango device servers
#
# v2.2 13/7/2022 Added doser1,2RampPowerTo, leemARRES
#
# v2.1 28/5/2021 Added leemRampTemperatureTo. This requires the PID controller to be on, and the gauge of the main chamber working.
#
# v2.0 25/02/2020 Autoselect day. Now leemSetDailyFolder is called at every experiment, and if the day is the same an an already existing folder, it does nothing. Otherwise, it creates the folder and resets the experiment number. Added time stamp in LEEMIV_ROI, LEEMIV
# v1.9 06/02/2020
#
# 06/02/2020 Changed number range in saving sequences from 3 digits to 4 digits. Removed LEEMIV_ROI_and_save, and added "saveImage" option in LEEMIV_ROI.
# 
# Juan de la Figuera juan.delafiguera@gmail.com

from datetime import date
import tango
import os
import numpy
import time
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d

def frange(start, stop=None, step=None):
    #Use float number in range() function
    # if stop and step argument is null set start=0.0 and step = 1.0
    # Change 20/6/2019 in order to output up to the last value stop.
    if stop == None:
        stop = start + 0.0
        start = 0.0
    if step == None:
        step = 1.0
    while True:
        if step > 0 and start >= stop+ step:
            break
        elif step < 0 and start <= stop+ step:
            break
        yield ("%g" % start) # return float number
        start = start + step
#end of function frange()


counter_filename="//hematite.labo/superficies/LEEM_Madrid/macros.dat"
name="000"

gaugeMCH=tango.DeviceProxy("leem/vacuum/gaugeMCH")
leem_pid=tango.DeviceProxy("leem/control/sample_leem_pid")
doser1_pid=tango.DeviceProxy("leem/control/doser_pid")
doser2_pid=tango.DeviceProxy("leem/control/doser2_pid")
leem2k=tango.DeviceProxy("leem/measurement/LEEM2k")
uview=tango.DeviceProxy("leem/measurement/Uview")
position=tango.DeviceProxy("leem/measurement/positionXY")

def leemSetPrefix(prefix):
    f=open(counter_filename,"w")
    today=date.today()
    dirname="%04d%02d%02d"%(today.year,today.month,today.day)
    f.write(prefix+","+dirname+","+"0")
    f.close()

def leemSetDailyFolder():
    (prefix,dayfolder,exp)=leem_getfolder()
    today=date.today()
    dayfolder="%04d%02d%02d"%(today.year,today.month,today.day)
    dayname=prefix+"/"+dayfolder
    if not os.path.exists(dayname):
        os.mkdir(dayname)
        print("Directory "+dayname+" Created ")
        f=open(counter_filename,"w")
        f.write(prefix+","+dayfolder+",0")
        f.close()
    else:
        print("Dayfolder "+dayname+" exists. Doing nothing.")
    
def leem_getfolder():
    if not os.path.exists(counter_filename):
        print "Error, no saved filename"
        exit()
    f=open(counter_filename,"r")
    count=f.readline()
    f.close()
    (prefix,dayfolder,exp)=count.split(",")
    return(prefix,dayfolder,int(exp))

def leem_makenextfolder_and_inc():
    (prefix,dayfolder,exp)=leem_getfolder()
    #Check that day folder exists
    today=date.today()
    dayfolder="%04d%02d%02d"%(today.year,today.month,today.day)
    dayname=prefix+"/"+dayfolder
    if not os.path.exists(dayname):
        os.mkdir(dayname)
        print("Directory "+dayname+" Created ")
        f=open(counter_filename,"w")
        f.write(prefix+","+dayfolder+",0")
        f.close()
        exp=0
    full=prefix+"/"+dayfolder+"/"+dayfolder+"_%03d"%exp
    name="%03d"%exp
    if not os.path.exists(full):
        os.mkdir(full)
        print("Directory "+full+" Created ")
    else:
        print("Directory "+full+" already exists")
    exp+=1
    f=open(counter_filename,"w")
    f.write(prefix+","+dayfolder+","+str(exp))
    f.close()
    return(full,name)

def leem_savesettings(name):
    f=open(name,"w")
    f.write("Position    : %s\n"%position.Position[1:-3])
    f.write("LEEM2k----------------------------\n")
    f.write("StartVoltage: %5.2f Volt\n"%leem2k.StartVoltage)
    f.write("Preset      : %s \n"%leem2k.Preset)
    f.write("Objective   : %7.1f mA\n"%leem2k.Objective)
    f.write("FieldLens   : %7.1f mA\n"%leem2k.FieldLens)
    f.write("TransferLens: %7.1f mA\n"%leem2k.TransferLens)
    f.write("IntermLens  : %7.1f mA\n"%leem2k.IntermLens)
    f.write("P1Lens      : %7.1f mA\n"%leem2k.P1Lens)
    f.write("MCHP        : %5.2f kV\n"%leem2k.ChannelPlateVoltage)
    f.write("Temperature : %5.1f C\n"%leem2k.SampleTemperature)
    f.write("Uview-----------------------------\n")
    f.write("Exposure    : %5.3f ms\n"%uview.Exposure)
    f.write("Average     : %5d \n"%uview.Average)
    f.write("ImageHeight : %4d \n"%uview.ImageHeight)
    f.write("ImageWidth  : %4d \n"%uview.ImageWidth)
    f.close()

def leemSaveSingleImage(exp=500,avg=0):
    """ leemSaveSingleImage( exposure (ms), average )
    
    BEWARE: 1 average means sliding average
    """
    (full,name)=leem_makenextfolder_and_inc()
    expname="IMG"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    oldAcq=uview.ContinousAcquisition
    uview.Exposure=exp
    uview.Average=avg
    uview.ContinousAcquisition=False
    uview.AcquireSingleImage()
    leem_savesettings(full+"/"+expname+".txt")
    while (uview.AcquisitionInProgress):
        pass
    res=uview.SaveImageAsDAT(full+"/"+expname)
    if (res=="0"):
        print "Succesfull saving %s"%expname
    uview.ContinousAcquisition=True
    uview.Exposure=oldExposure
    uview.Average=oldAverage

def leemSequenceImages(exp=400,avg=1,n=-1,delay=1.0):
    """ leemSequenceImage (exposure (ms), average, number_of_images (-1=infinite), delay (s)
    
    Save sequence of images. For infinite, press CTRL-C to stop.
     
    BEWARE: 1 average means sliding average
    """
    (full,name)=leem_makenextfolder_and_inc()
    expname="SEQ"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    oldAcq=uview.ContinousAcquisition
    uview.Exposure=exp
    uview.Average=avg
    uview.ContinousAcquisition=True
    leem_savesettings(full+"/"+expname+".txt")
    try:
        if (n==-1):
            a=0
            while (1):
                savename=expname+"_%05d"%a
                if (uview.SaveImageAsDAT(full+"/"+savename)=="0"):
                    print "Saved %s"%savename
                a+=1
                time.sleep(delay)
        else:
            for a in range(n):
                savename=expname+"_%05d"%a
                if (uview.SaveImageAsDAT(full+"/"+savename)=="0"):
                    print "Saved %s"%savename
                time.sleep(delay)
    except KeyboardInterrupt:
        print "Ok, so you want to finish. Let me clean up."
    uview.ContinousAcquisition=True
    uview.Exposure=oldExposure
    uview.Average=oldAverage

def leemIV(E0,Ef,dE,exp=400.0,avg=0,repeat=False):
    """ leemIV (Initial Energy (V), Final Energy (V), increment E (V), exposure (ms), average, repeat (default=False)
    
    Save sequence of images changing energy and objective.
    For repeated loops (repeat=True), press CTRL-C to finish.
    
    BEWARE: 1 average means sliding average
    """
    (full,name)=leem_makenextfolder_and_inc()
    expname="LEEMIV"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    oldAcq=uview.ContinousAcquisition
    uview.Exposure=exp
    uview.Average=avg
    uview.ContinousAcquisition=True
    leem_savesettings(full+"/"+expname+".txt")
    f=open(full+"/LOG.txt","w")
    f.write("# Image number  Energy (eV) time\n")
    a=0
    try:
        while (True):
            #e=frange(E0,Ef,dE)
            e=numpy.arange(E0,Ef+dE,dE)
            for i in e:
                leem2k.StartVoltage=float(i)
                t=time.localtime()
                timenow=time.strftime("%c", t)
                print "Image %d Energy %f Time %s"%(a,float(i),timenow)
                f.write("%d %f %s\n"%(a,float(i),timenow))
                uview.AcquireSingleImage()
                while (uview.AcquisitionInProgress):
                    pass
                savename=expname+"_%05d"%a
                if (uview.SaveImageAsDAT(full+"/"+savename)=="0"):
                    print "Saved %s"%savename
                a+=1
            if (repeat==False):
                break
    except KeyboardInterrupt:
        print "Ok, ok, stopping adquisition. Let me clean up"
    f.close()
    uview.ContinousAcquisition=True
    uview.Exposure=oldExposure
    uview.Average=oldAverage


def leemIV_ROI(E0,Ef,dE,exp=400.0,avg=0,repeat=False,plot=False,saveImage=False):
    """ leemIV (Initial Energy (V), Final Energy (V), increment E (V), exposure (ms), average, repeat (default=False), plot (default=False)
    
    Save intensity of ROI changing energy, and optionally, plot it.
    For repeated loops (repeat=True), press CTRL-C to finish.
    
    BEWARE: 1 average means sliding average
    """
    (full,name)=leem_makenextfolder_and_inc()
    expname="LEEMIV"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    oldAcq=uview.ContinousAcquisition
    uview.Exposure=exp
    uview.Average=avg
    uview.ContinousAcquisition=True
    leem_savesettings(full+"/"+expname+".txt")
    f=open(full+"/LOG.txt","w")
    f.write("# Image number  Energy (eV) ROI1 (arb.u.) time\n")
    a=0
    fig=plt.figure()
    ax=fig.add_subplot(111)
    try:
        while (True):
            #e=frange(E0,Ef,dE)
            e=numpy.arange(E0,Ef+dE,dE,dtype="float")
            rois=numpy.zeros(len(e))
            k=0
            for i in e:
                leem2k.StartVoltage=i
                uview.AcquireSingleImage()
                while (uview.AcquisitionInProgress):
                    pass
                rois[k]=float(uview.IntensityROI1)
                t=time.localtime()
                timenow=time.strftime("%c", t)
                if (saveImage==True):
                    savename=expname+"_%05d"%a
                    if (uview.SaveImageAsDAT(full+"/"+savename)=="0"):
                        print "Saved %s"%savename
                print "Image %d Energy %f ROI1 %f time %s"%(a,i,rois[k],timenow)
                f.write("%d %f %f %s\n"%(a,i,rois[k],timenow))
                a+=1
                k+=1
            if (plot==True):
                ax.plot(e,rois)
                fig.show()
                fig.canvas.draw()
            f.flush()
            if (repeat==False):
               break
    except KeyboardInterrupt:
        print "Ok, ok, you want me to stop. Cleaning up."
    f.close()
    uview.ContinousAcquisition=True
    uview.Exposure=oldExposure
    uview.Average=oldAverage


def leemIVandObj(E0,Ef,dE,startObj,endObj, exp=400.0,avg=0):
    """ leemIVandObj (Initial Energy (V), Final Energy (V), increment E (V), Start Objective (mA), End Objective (mA), exposure (ms), average
    
    Save sequence of images changing energy and objective.
    
    BEWARE: 1 average means sliding average
    """
    (full,name)=leem_makenextfolder_and_inc()
    expname="LEEMIV"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    oldAcq=uview.ContinousAcquisition
    uview.Exposure=exp
    uview.Average=avg
    uview.ContinousAcquisition=True
    leem_savesettings(full+"/"+expname+".txt")
    f=open(full+"/LOG.txt","w")
    f.write("# Image number  Energy (eV) Objective (mA)\n")
    e=frange(E0,Ef,dE)
    a=0
    for i in e:
        leem2k.StartVoltage=float(i)
        leem2k.Objective=float((endObj-startObj)*(float(i)-E0)/(Ef-E0)+startObj)
        print "Image %d Energy %f Objective %f"%(a,float(i),float((endObj-startObj)*(float(i)-E0)/(Ef-E0)+startObj))
        f.write("%d %f %f\n"%(a,float(i),float((endObj-startObj)*(float(i)-E0)/(Ef-E0)+startObj)))
        uview.AcquireSingleImage()
        while (uview.AcquisitionInProgress):
            pass
        #uview.SaveImageAsPNG(expname)
        savename=expname+"_%05d"%a
        if (uview.SaveImageAsDAT(full+"/"+savename)=="0"):
            print "Saved %s"%savename
        a+=1
    f.close()
    uview.ContinousAcquisition=True
    uview.Exposure=oldExposure
    uview.Average=oldAverage

def pidRampTo(pid,final,step=1.0,time_step=1.0,pressure_limit=1):
    """ pidRampTo (desired_setpoint, step, time_step, pressure_limit)
    Ramp PID setpoint (PID must be activated before!!)
    Parameters:
        desired: final desired setpoint
        step: setpoint change per step (default 1)
        time_step: waiting time per step (deault is 1s)"""
    start=pid.SetPoint
    if (start>final):
        r=numpy.arange(start,final,-step)
    else:
        r=numpy.arange(start,final,step)
    for a in r:
        pid.SetPoint=a
        print("Going to %f"%a)
        while (gaugeMCH.Pressure_IG1 > pressure_limit):
             time.sleep(10)
        time.sleep(time_step)
    
def leemRampTemperatureTo(temp,temp_step=1.0,time_step=1.0,pressure_limit=1):
    """ leemRampTemperatureTo (temp, temp_step, time_step, pressure_limit)
    Ramp temperature using PID (must be on before!)
    Parameters: 
        temp: final temperature (in C)
        temp_step: temperature change per step (default 1C)
        time_step: waiting time per step (default 1s)
        pressure_limit: if pressure above the limit, will wait (default 1, no limit) """ 
    pidRampTo(leem_pid,temp,temp_step,time_step,pressure_limit)
    
def doser1RampPowerTo(power,power_step=1.0,time_step=1.0,pressure_limit=1):
    """ leemRampTemperatureTo (temp, temp_step, time_step, pressure_limit)
    Ramp temperature using PID (must be on before!)
    Parameters: 
        power: final power (in W)
        power_step: temperature change per step (default 1C)
        time_step: waiting time per step (default 1s)
        pressure_limit: if pressure above the limit, will wait (default 1, no limit) """ 
    #pid=tango.DeviceProxy("leem/power/doser1_pid")
    pidRampTo(doser1_pid,power,power_step,time_step,pressure_limit)

def doser1RampPowerTo(power,power_step=1.0,time_step=1.0,pressure_limit=1):
    """ leemRampTemperatureTo (temp, temp_step, time_step, pressure_limit)
    Ramp temperature using PID (must be on before!)
    Parameters: 
        power: final power (in W)
        power_step: temperature change per step (default 1C)
        time_step: waiting time per step (default 1s)
        pressure_limit: if pressure above the limit, will wait (default 1, no limit) """ 
    #pid=tango.DeviceProxy("leem/power/doser1_pid")
    pidRampTo(doser2_pid,power,power_step,time_step,pressure_limit)



def leemARRESset():
    """ leemARRESset()
    Reads normal incidence IDX,IDY,IEX,IEY and ask to change the incidence for two endpoints.
    Used as reciprocal space positions in leemARRESrun()
    """
    b = zeros((3,4)) # Array to keep the settings for the ARRES scans. b[0] is the 0º position, b[1] is the 1st endpoint, b[2] is the 2nd endpoint. Second coordinate is (IllDefX,IllDefY,ImEqX,ImEqY)
    b[0]=leemReadDeflection()
    print("Normal Incidence condition IDX,IDY,IEX,IEY = ",b[0])
    raw_input("Move to endpoint 1 in reciprocal space and press enter") # Change to input() in Python3
    b[1]=leemReadDeflection()
    print("Endpoint 1 condition IDX,IDY,IEX,IEY = ",b[1])
    leemSetDeflection(b[0])
    raw_input("Move to endpoint 2 in reciprocal space and press enter") # Change to input() in Python3
    b[2]=leemReadDeflection()
    leemSetDeflection(b[0])
    print("Endpoint 2 condition IDX,IDY,IEX,IEY = ",b[1])
    for i in range(0,1):
        for j in range(0,3):
            if (b[i,j]>200):
                b[i,j]=0
    
    return(b)
    
def leemARRESrun(E0,Ef,nE,nk,b,exp=400,avg=0,):
    """ leemARRESrun(E0,Ef,nE,nk,b,exp=400,avg=0)
    Runs a Angle-Resolved Reflection Electron Spectroscopy scan. Needs energy limits (E0,Ef, nE), and number of k points (nk).
    The incidence settings are read by leemARRESset().
    """
    (full,name)=leem_makenextfolder_and_inc()
    expname="ARRES"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    oldAcq=uview.ContinousAcquisition
    uview.Exposure=exp
    uview.Average=avg
    uview.ContinousAcquisition=True
    leem_savesettings(full+"/"+expname+".txt")
    
    f=open(full+"/"+expname+"_deflection.txt","w")
    f.write("Normal Incidence condition IDX %f IDY %f IEX %f IEY %f \n"%(b[0,0],b[0,1],b[0,2],b[0,3]))
    f.write("Endpoint 1 condition IDX %f IDY %f IEX %f IEY %f \n"%(b[1,0],b[1,1],b[1,2],b[1,3]))
    if (len(b>2)):
        f.write("Endpoint 2 condition IDX %f IDY %f IEX %f IEY %f \n"%(b[2,0],b[2,1],b[2,2],b[2,3]))    
    f.close()
    
    
    f=open(full+"/LOG0.txt","w")
    f.write("# Imagenumber k Energy(eV) roi time\n")
    a=0
    a_k=0
    a_e=0
    e=numpy.linspace(E0,Ef,nE)
    k=numpy.linspace(0.0,1.0,nk)
    arres0=numpy.zeros((nk,nE))
    interpIllDefX = interp1d([0,1],[b[0,0],b[1,0]])
    interpIllDefY = interp1d([0,1],[b[0,1],b[1,1]])
    interpImEqX = interp1d([0,1],[b[0,2],b[1,2]])
    interpImEqY = interp1d([0,1],[b[0,3],b[1,3]])
    
    for j in k:
        a_e=0
        leem2k.IllDefX=interpIllDefX(j)
        leem2k.IllDefY=interpIllDefY(j)
        leem2k.ImEqX=interpImEqX(j)
        leem2k.ImEqY=interpImEqY(j)
        print("%5.1f"%interpIllDefX(j),"%5.1f"%interpIllDefY(j),"%5.1f"%interpImEqX(j),"%5.1f"%interpImEqY(j))
        for i in e:
            leem2k.StartVoltage=float(i)
            t=time.localtime()
            timenow=time.strftime("%c", t)
            uview.AcquireSingleImage()
            while (uview.AcquisitionInProgress):
                pass
            savename=expname+"_0_%05d"%a
            if (uview.SaveImageAsDAT(full+"/"+savename)=="0"):
                print "%s %f %f "%(savename,j,i)
            roi=float(uview.IntensityROI1)
            arres0[a_k,a_e]=roi
            f.write("%d %f %f %f %s\n"%(a,j,i,roi,timenow))
            a+=1
            a_e+=1
        print
        a_k+=1
        
    plt.subplot(121)
    plt.imshow(flip(arres0.swapaxes(0,1),1),aspect="auto",origin="lower")
    plt.yticks( arange(nE), arange(E0,Ef,1+(Ef-E0)/(nE)))
    plt.show()
    f.close()
    leemSetDeflection(b[0])
    numpy.save(full+"/arres0.npy",arres0)
    savefig(full+"/arres0.pdf")
    
    # Check if we have 2 directions to measure. If only one, finish up.
    if (len(b)==2):
        uview.ContinousAcquisition=True
        uview.Exposure=oldExposure
        uview.Average=oldAverage
        return(arres0)
    
    f=open(full+"/LOG1.txt","w")
    f.write("# Imagenumber k Energy(eV) roi time\n")
    a=0
    a_k=0
    a_e=0
    e=numpy.linspace(E0,Ef,nE)
    k=numpy.linspace(0.0,1.0,nk)
    arres1=numpy.zeros((nk,nE))
    interpIllDefX = interp1d([0,1],[b[0,0],b[2,0]])
    interpIllDefY = interp1d([0,1],[b[0,1],b[2,1]])
    interpImEqX = interp1d([0,1],[b[0,2],b[2,2]])
    interpImEqY = interp1d([0,1],[b[0,3],b[2,3]])
    
    for j in k:
        a_e=0
        leem2k.IllDefX=interpIllDefX(j)
        leem2k.IllDefY=interpIllDefY(j)
        leem2k.ImEqX=interpImEqX(j)
        leem2k.ImEqY=interpImEqY(j)
        print("%5.1f"%interpIllDefX(j),"%5.1f"%interpIllDefY(j),"%5.1f"%interpImEqX(j),"%5.1f"%interpImEqY(j))
        for i in e:
            leem2k.StartVoltage=float(i)
            t=time.localtime()
            timenow=time.strftime("%c", t)
            uview.AcquireSingleImage()
            while (uview.AcquisitionInProgress):
                pass
            savename=expname+"_1_%05d"%a
            if (uview.SaveImageAsDAT(full+"/"+savename)=="0"):
                print "%s %f %f "%(savename,j,i)
            roi=float(uview.IntensityROI1)
            arres1[a_k,a_e]=roi
            f.write("%d %f %f %f %s\n"%(a,j,i,roi,timenow))
            a+=1
            a_e+=1
        print
        a_k+=1 
        
    plt.subplot(122)
    plt.imshow(arres1.swapaxes(0,1),aspect="auto",origin="lower")
    plt.yticks(array([]),array([]))
    plt.show()
    f.close()
    leemSetDeflection(b[0])
    numpy.save(full+"/arres1.npy",arres1)
    savefig(full+"/arres1.pdf")
    uview.ContinousAcquisition=True
    uview.Exposure=oldExposure
    uview.Average=oldAverage
    return(arres0,arres1)
    
def leemSetDeflection(beam):
    leem2k.IllDefX = beam[0]
    leem2k.IllDefY = beam[1]
    leem2k.ImEqX = beam[2]
    leem2k.ImEqY = beam[3]
        
def leemReadDeflection():
    idx=leem2k.IllDefX
    idy=leem2k.IllDefY
    iex=leem2k.ImEqX
    iey=leem2k.ImEqY
    return(array([idx,idy,iex,iey]))
