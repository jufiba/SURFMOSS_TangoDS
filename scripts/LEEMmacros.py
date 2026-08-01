#!/usr/bin/python
# LEEM Madrid Macros
# Simple acquisition using tango device servers
#
# v3.1 01/08/2026 Added a Qt acquisition GUI, in LEEMgui.py, opened with gui(). It exposes single image, sequence, IV, IV with ROI, IV with objective and the temperature ramp, each with its parameters, a Stop button and a log box. ARRES stays command line only because leemARRESset() asks for input() at the terminal. Acquisitions run in a worker thread, so a stop cannot use CTRL-C: instead leem_abort is set and the loops poll it through leem_checkstop(), which raises KeyboardInterrupt so a GUI stop unwinds through exactly the same cleanup as CTRL-C. The sleeps in leemSequenceImages and leemRampTemperatureROI now use leem_abort.wait(), so stopping does not have to wait out the delay. leemIVandObj gained the KeyboardInterrupt handler it never had, which also fixes CTRL-C there leaving the camera stopped at the wrong exposure.
#
# v3.0 31/07/2026 Removed all live plotting, so the macros no longer open windows and no longer depend on the ipython --pylab namespace. show(), savefig(), zeros(), array() and flip() were being used without ever being imported, and only resolved because the file is run into a --pylab session; they are now numpy./Figure. calls. Plots are written to files with matplotlib's Figure object API (no pyplot, no backend, no global state), so they also work from a worker thread. leemIV_ROI has lost its plot parameter, it always writes plot.png/plot.pdf now, and no longer crashes on its default arguments (fig was used outside the plot guard). leemARRESrun writes arres0/arres1 .pdf and .png and no longer leaves the camera stopped on the two-direction path. Fixed a python2 leftover bare print. The module can now be imported, which is what the GUI needs.
#
# v2.9 31/07/2026 leemSaveSingleImage and leemSequenceImages now only stop the camera when the requested exposure differs from the current one. Otherwise the camera is left running (started if it was stopped) and the average is changed live, which saves the thrown-away image. BEWARE: on that path leemSaveSingleImage no longer triggers a fresh exposure, it saves the frame UView currently holds, so with avg=1 (sliding average) the image can include frames from before the call. Note also that with the camera running ContinousAcquisition reads True forever, so the single-image trigger and its wait loop can only be used on the stopped path. Exposure and average are now optional in both commands: left out, the value already set in the camera is used, so calling them with no arguments never stops the camera. This changes the old no-argument behaviour, which forced 500ms/avg 0 for a single image and 400ms/avg 1 for a sequence.
#
# v2.8 27/07/2026 Modified to stop Continuous acquisition for every sequence that requires synchronization (modified also the UView device server to use only a RW ContinuousAcquisition variable instead of a W ContinuousAcquisition and a R AcquisitionInProgress, which I think were stepping on each other). Note there is still a typo: Continous instead of Continuous. Also had to add a delay after switching on and off continuous mode, and we also have to throw away one image after such changes.
#
# v2.7 17/07/2026 Modified to stop acquisition before any exposure change
#
# v2.6 26/9/2024 Modified for python3 again...
#
# v2.5 23/4/2024 Added CONTROL-C check in leemRampTemperaureROI
#
# v2.4 21/2/2024 rampLEEMROI
#
# v2.3 Minor cleaning
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
# 20/02/2023 Adapted to Python3.
#
# Juan de la Figuera juan.delafiguera@gmail.com

__version__ = "3.1"

from datetime import date
import tango
import os
import numpy
import time
import threading
from matplotlib.figure import Figure
from scipy.interpolate import interp1d

# Set by the GUI Stop button. The acquisition loops poll it through
# leem_checkstop() and raise KeyboardInterrupt, so a GUI stop unwinds through
# exactly the same cleanup code as CTRL-C from the command line.
leem_abort=threading.Event()

def leem_checkstop():
    """ Raise KeyboardInterrupt if a stop has been requested from the GUI. """
    if leem_abort.is_set():
        raise KeyboardInterrupt

def gui():
    """ Open the acquisition GUI. Imported lazily so that a plain command line
    session does not need PySide6. """
    from LEEMgui import leem_gui_main
    return leem_gui_main()

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


counter_filename="/home/tvips/Superficies/LEEM_Madrid/macros.dat"
name="000"

#gaugeMCH=tango.DeviceProxy("leem/vacuum/gaugeMCH")
leem_pid=tango.DeviceProxy("leem/control/sample_leem_pid")
doser1_pid=tango.DeviceProxy("leem/control/doser_pid")
doser2_pid=tango.DeviceProxy("leem/control/doser2_pid")
leem2k=tango.DeviceProxy("leem/measurement/LEEM2k")
uview=tango.DeviceProxy("leem/measurement/Uview")
position=tango.DeviceProxy("leem/measurement/positionXY")

def leemSetDailyFolder():
    (wprefix,prefix,dayfolder,exp)=leem_getfolder()
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
        print("Error, no saved filename")
        exit()
    f=open(counter_filename,"r")
    count=f.readline()
    f.close()
    (wprefix,prefix,dayfolder,exp)=count.split(",")
    return(wprefix,prefix,dayfolder,int(exp))

def leem_makenextfolder_and_inc():
    (wprefix,prefix,dayfolder,exp)=leem_getfolder()
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
    wfull=wprefix+"/"+dayfolder+"/"+dayfolder+"_%03d"%exp
    name="%03d"%exp
    if not os.path.exists(full):
        os.mkdir(full)
        print("Directory "+full+" Created ")
    else:
        print("Directory "+full+" already exists")
    exp+=1
    f=open(counter_filename,"w")
    f.write(wprefix+","+prefix+","+dayfolder+","+str(exp))
    f.close()
    return(wfull,full,name)

def leem_savesettings(name):
    f=open(name,"w")
    #f.write("Position    : %s\n"%position.Position[1:-3])
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

def leem_exposure_differs(current,exp):
    """ True if the camera is not already at the requested exposure (ms).

    Only an exposure change needs the camera stopped and restarted, which costs
    a thrown-away image because of the UView/TVIPS triggering problem. Compared
    with a tolerance because Exposure is read back as a float from UView.
    """
    return abs(current-exp)>0.01

def leemSaveSingleImage(exp=None,avg=None):
    """ leemSaveSingleImage( exposure (ms), average )

    Both are optional. Left out, whatever the camera is already set to is used.

    BEWARE: 1 average means sliding average
    """
    (wfull,full,name)=leem_makenextfolder_and_inc()
    expname="IMG"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    if exp is None:
        exp=oldExposure
    if avg is None:
        avg=oldAverage
    restarted=leem_exposure_differs(oldExposure,exp)
    if restarted:
        uview.ContinousAcquisition=False
        time.sleep(0.5)
        uview.Exposure=exp
        uview.Average=avg
        uview.AcquireSingleImage() # Throw one away
        while (uview.ContinousAcquisition):
            pass
        uview.AcquireSingleImage()
        while (uview.ContinousAcquisition):
            pass
    else:
        # Exposure already correct, so keep the camera running and grab the
        # frame it has. BEWARE: with the camera running, ContinousAcquisition
        # reads True forever, so AcquireSingleImage and the wait loops above
        # must not be used here.
        if avg!=oldAverage:
            uview.Average=avg
        if not uview.ContinousAcquisition:
            uview.ContinousAcquisition=True
            time.sleep(0.5)
    leem_savesettings(full+"/"+expname+".txt")
    res=uview.SaveImageAsDAT(wfull+"/"+expname)
    if (res=="0"):
        print("Succesfull saving %s"%expname)
    if restarted:
        uview.Exposure=oldExposure
        uview.Average=oldAverage
        uview.ContinousAcquisition=True
    elif avg!=oldAverage:
        uview.Average=oldAverage

def leemSequenceImages(exp=None,avg=None,n=-1,delay=1.0):
    """ leemSequenceImage (exposure (ms), average, number_of_images (-1=infinite), delay (s)

    Save sequence of images. For infinite, press CTRL-C to stop.

    Exposure and average are optional. Left out, whatever the camera is already
    set to is used.

    BEWARE: 1 average means sliding average
    """
    (wfull,full,name)=leem_makenextfolder_and_inc()
    expname="SEQ"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    if exp is None:
        exp=oldExposure
    if avg is None:
        avg=oldAverage
    restarted=leem_exposure_differs(oldExposure,exp)
    if restarted:
        uview.ContinousAcquisition=False
        uview.Exposure=exp
        uview.Average=avg
        time.sleep(0.5)
        uview.ContinousAcquisition=True
        time.sleep(0.5)
    else:
        # Exposure already correct, so leave the camera running.
        if avg!=oldAverage:
            uview.Average=avg
        if not uview.ContinousAcquisition:
            uview.ContinousAcquisition=True
            time.sleep(0.5)
    leem_savesettings(full+"/"+expname+".txt")
    try:
        if (n==-1):
            a=0
            while (1):
                leem_checkstop()
                savename=expname+"_%05d"%a
                if (uview.SaveImageAsDAT(wfull+"/"+savename)=="0"):
                    print("Saved %s"%savename)
                a+=1
                leem_abort.wait(delay)
        else:
            for a in range(n):
                leem_checkstop()
                savename=expname+"_%05d"%a
                if (uview.SaveImageAsDAT(wfull+"/"+savename)=="0"):
                    print("Saved %s"%savename)
                leem_abort.wait(delay)
    except KeyboardInterrupt:
        print("Ok, so you want to finish. Let me clean up.")
    if restarted:
        uview.ContinousAcquisition=False
        uview.Exposure=oldExposure
        uview.Average=oldAverage
        uview.ContinousAcquisition=True
    elif avg!=oldAverage:
        uview.Average=oldAverage

def leemIV(E0,Ef,dE,exp=400.0,avg=0,repeat=False):
    """ leemIV (Initial Energy (V), Final Energy (V), increment E (V), exposure (ms), average, repeat (default=False)
    
    Save sequence of images changing energy and objective.
    For repeated loops (repeat=True), press CTRL-C to finish.
    
    BEWARE: 1 average means sliding average
    """
    (wfull,full,name)=leem_makenextfolder_and_inc()
    expname="LEEMIV"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    uview.ContinousAcquisition=False
    time.sleep(0.5)
    uview.Exposure=exp
    uview.Average=avg
    leem_savesettings(full+"/"+expname+".txt")
    f=open(full+"/LOG.txt","w")
    f.write("# Image number  Energy (eV) time\n")

    uview.AcquireSingleImage() # Throw one away
    while (uview.ContinousAcquisition):
        pass
    a=0
    try:
        while (True):
            #e=frange(E0,Ef,dE)
            e=numpy.arange(E0,Ef+dE,dE)
            for i in e:
                leem_checkstop()
                leem2k.StartVoltage=float(i)
                t=time.localtime()
                timenow=time.strftime("%c", t)
                print("Image %d Energy %f Time %s"%(a,float(i),timenow))
                f.write("%d %f %s\n"%(a,float(i),timenow))
                uview.AcquireSingleImage()
                while (uview.ContinousAcquisition):
                    pass
                savename=expname+"_%05d"%a
                if (uview.SaveImageAsDAT(wfull+"/"+savename)=="0"):
                    print("Saved %s"%savename)
                a+=1
            if (repeat==False):
                break
    except KeyboardInterrupt:
        print("Ok, ok, stopping adquisition. Let me clean up")
    f.close()
    uview.Exposure=oldExposure
    uview.Average=oldAverage
    uview.ContinousAcquisition=True


def leemIV_ROI(E0,Ef,dE,exp=400.0,avg=0,repeat=False,roi=1,saveImage=False):
    """ leemIV (Initial Energy (V), Final Energy (V), increment E (V), exposure (ms), average, repeat (default=False), roi (default=1, or use 2 for two boxes), saveImage (default=False)

    Save intensity of ROI changing energy. The curve is written to plot.png and
    plot.pdf in the experiment folder, no window is opened.
    For repeated loops (repeat=True), press CTRL-C to finish.

    BEWARE: 1 average means sliding average
    """
    (wfull,full,name)=leem_makenextfolder_and_inc()
    expname="LEEMIV"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    uview.ContinousAcquisition=False
    time.sleep(0.5)
    uview.Exposure=exp
    uview.Average=avg
    leem_savesettings(full+"/"+expname+".txt")
    f=open(full+"/LOG.txt","w")
    uview.AcquireSingleImage() # Throw one away
    while (uview.ContinousAcquisition):
        pass
    f.write("# Image number  Energy (eV) ROI1 (arb.u.) time\n")
    a=0
    fig=Figure()
    if (roi==1):
        ax=fig.add_subplot(111)
    else:
        ax=fig.add_subplot(211)
        ax2=fig.add_subplot(212)
    try:
        while (True):
            #e=frange(E0,Ef,dE)
            e=numpy.arange(E0,Ef+dE,dE,dtype="float")
            rois=numpy.zeros(len(e))
            if (roi!=1):
                rois2=numpy.zeros(len(e))
            k=0
            for i in e:
                leem_checkstop()
                leem2k.StartVoltage=i
                uview.AcquireSingleImage()
                while (uview.ContinousAcquisition):
                    pass
                rois[k]=float(uview.IntensityROI1)
                if (roi==2):
                    rois2[k]=float(uview.IntensityROI2)
                t=time.localtime()
                timenow=time.strftime("%c", t)
                if (saveImage==True):
                    savename=expname+"_%05d"%a
                    if (uview.SaveImageAsDAT(wfull+"/"+savename)=="0"):
                        print("Saved %s"%savename)
                if (roi==1):
                    print("Image %d Energy %f ROI1 %f time %s"%(a,i,rois[k],timenow))
                    f.write("%d %f %f %s\n"%(a,i,rois[k],timenow))
                else:
                    print("Image %d Energy %f ROI1 %f ROI2 %f time %s"%(a,i,rois[k],rois2[k],timenow))
                    f.write("%d %f %f %f %s\n"%(a,i,rois[k],rois2[k],timenow))
                a+=1
                k+=1
            ax.plot(e,rois)
            if (roi!=1):
                ax2.plot(e,rois2)
            # Rewritten every pass, so the file can be watched while repeating.
            fig.savefig(full+"/plot.png")
            f.flush()
            if (repeat==False):
               break
    except KeyboardInterrupt:
        print("Ok, ok, you want me to stop. Cleaning up.")
    f.close()
    fig.savefig(full+"/plot.pdf")
    fig.savefig(full+"/plot.png")
    uview.Exposure=oldExposure
    uview.Average=oldAverage
    uview.ContinousAcquisition=True


def leemIVandObj(E0,Ef,dE,startObj,endObj, exp=400.0,avg=0):
    """ leemIVandObj (Initial Energy (V), Final Energy (V), increment E (V), Start Objective (mA), End Objective (mA), exposure (ms), average
    
    Save sequence of images changing energy and objective.
    
    BEWARE: 1 average means sliding average
    """
    (wfull,full,name)=leem_makenextfolder_and_inc()
    expname="LEEMIV"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    uview.ContinousAcquisition=False
    time.sleep(0.5)
    uview.Exposure=exp
    uview.Average=avg
    leem_savesettings(full+"/"+expname+".txt")
    uview.AcquireSingleImage() # Throw one away
    while (uview.ContinousAcquisition):
        pass
    f=open(full+"/LOG.txt","w")
    f.write("# Image number  Energy (eV) Objective (mA)\n")
    e=frange(E0,Ef,dE)
    a=0
    try:
        for i in e:
            leem_checkstop()
            leem2k.StartVoltage=float(i)
            leem2k.Objective=float((endObj-startObj)*(float(i)-E0)/(Ef-E0)+startObj)
            print("Image %d Energy %f Objective %f"%(a,float(i),float((endObj-startObj)*(float(i)-E0)/(Ef-E0)+startObj)))
            f.write("%d %f %f\n"%(a,float(i),float((endObj-startObj)*(float(i)-E0)/(Ef-E0)+startObj)))
            uview.AcquireSingleImage()
            while (uview.ContinousAcquisition):
                pass
            #uview.SaveImageAsPNG(expname)
            savename=expname+"_%05d"%a
            if (uview.SaveImageAsDAT(wfull+"/"+savename)=="0"):
                print("Saved %s"%savename)
            a+=1
    except KeyboardInterrupt:
        print("Ok, so you want to finish. Let me clean up.")
    f.close()
    uview.Exposure=oldExposure
    uview.Average=oldAverage
    uview.ContinousAcquisition=True

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
        #while (gaugeMCH.Pressure_IG1 > pressure_limit):
        #     time.sleep(10)
        time.sleep(time_step)

def leemRampTemperatureROI(temp, step=1.0, time_step=1.0, exp=100, avg=0, saveImage=False):
    """ leemRampTemperatureROI( temp, temp_step=1.0, time_step=1.0, exposure=100, average=0, saveimage=False)"""
    (wfull,full,name)=leem_makenextfolder_and_inc()
    expname="TEMPRAMP"+name
    start=leem_pid.SetPoint
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    uview.ContinousAcquisition=False
    time.sleep(0.5)
    uview.Exposure=exp
    uview.Average=avg
    leem_savesettings(full+"/"+expname+".txt")
    f=open(full+"/LOG.txt","w")
    uview.AcquireSingleImage() # Throw one away
    while (uview.ContinousAcquisition):
        pass
    f.write("# Image number Temp SetTemp ROI time\n")
    if (start>temp):
        r=numpy.arange(start,temp,-step)
    else:
        r=numpy.arange(start,temp,step)
    c=0
    try:
        for a in r:
            leem_checkstop()
            leem_pid.SetPoint=a
            print("Going to %f"%a)
            leem_abort.wait(time_step)
            temp=leem2k.SampleTemperature
            uview.AcquireSingleImage()
            while (uview.ContinousAcquisition):
                pass
            roi=float(uview.IntensityROI1)
            t=time.localtime()
            timenow=time.strftime("%c", t)
            if (saveImage==True):
                savename=expname+"_%05d"%c
                if (uview.SaveImageAsDAT(wfull+"/"+savename)=="0"):
                   print("Saved %s"%savename)
            print("Image %d Temp %f SetTemp %f ROI1 %f time %s"%(c,temp,a,roi,timenow))
            f.write("%d %f %f %f %s\n"%(c,temp,a,roi,timenow))
            c+=1
    except KeyboardInterrupt:
       print("Ok, ok, you want me to stop. Cleaning up.")
    f.flush()
    f.close()
    uview.Exposure=oldExposure
    uview.Average=oldAverage
    uview.ContinousAcquisition=True

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

def doser2RampPowerTo(power,power_step=1.0,time_step=1.0,pressure_limit=1):
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
    b = numpy.zeros((3,4)) # Array to keep the settings for the ARRES scans. b[0] is the 0 position, b[1] is the 1st endpoint, b[2] is the 2nd endpoint. Second coordinate is (IllDefX,IllDefY,ImEqX,ImEqY)
    b[0]=leemReadDeflection()
    print("Normal Incidence condition IDX,IDY,IEX,IEY = ",b[0])
    input("Move to endpoint 1 in reciprocal space and press enter") # Change to input() in Python3
    b[1]=leemReadDeflection()
    print("Endpoint 1 condition IDX,IDY,IEX,IEY = ",b[1])
    leemSetDeflection(b[0])
    input("Move to endpoint 2 in reciprocal space and press enter") # Change to raw_input() in Python2
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
    (wfull,full,name)=leem_makenextfolder_and_inc()
    expname="ARRES"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    uview.ContinousAcquisition=False
    time.sleep(0.5)
    uview.Exposure=exp
    uview.Average=avg
    leem_savesettings(full+"/"+expname+".txt")
    uview.AcquireSingleImage() # Throw one away
    while (uview.ContinousAcquisition):
        pass
    
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
            while (uview.ContinousAcquisition):
                pass
            savename=expname+"_0_%05d"%a
            if (uview.SaveImageAsDAT(wfull+"/"+savename)=="0"):
                print("%s %f %f "%(savename,j,i))
            roi=float(uview.IntensityROI1)
            arres0[a_k,a_e]=roi
            f.write("%d %f %f %f %s\n"%(a,j,i,roi,timenow))
            a+=1
            a_e+=1
        print()
        a_k+=1
        
    fig0=Figure()
    ax0=fig0.add_subplot(111)
    ax0.imshow(numpy.flip(arres0.swapaxes(0,1),1),aspect="auto",origin="lower")
    f.close()
    leemSetDeflection(b[0])
    numpy.save(full+"/arres0.npy",arres0)
    fig0.savefig(full+"/arres0.pdf")
    fig0.savefig(full+"/arres0.png")
    
    # Check if we have 2 directions to measure. If only one, finish up.
    if (len(b)==2):
        uview.Exposure=oldExposure
        uview.Average=oldAverage
        uview.ContinousAcquisition=True
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
            while (uview.ContinousAcquisition):
                pass
            savename=expname+"_1_%05d"%a
            if (uview.SaveImageAsDAT(wfull+"/"+savename)=="0"):
                print("%s %f %f "%(savename,j,i))
            roi=float(uview.IntensityROI1)
            arres1[a_k,a_e]=roi
            f.write("%d %f %f %f %s\n"%(a,j,i,roi,timenow))
            a+=1
            a_e+=1
        print()
        a_k+=1 
        
    fig1=Figure()
    ax1=fig1.add_subplot(111)
    ax1.imshow(arres1.swapaxes(0,1),aspect="auto",origin="lower")
    f.close()
    leemSetDeflection(b[0])
    numpy.save(full+"/arres1.npy",arres1)
    fig1.savefig(full+"/arres1.pdf")
    fig1.savefig(full+"/arres1.png")
    uview.Exposure=oldExposure
    uview.Average=oldAverage
    uview.ContinousAcquisition=True
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
    return(numpy.array([idx,idy,iex,iey]))
