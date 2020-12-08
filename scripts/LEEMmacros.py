#!/usr/bin/python
# LEEM Madrid Macros
# Simple acquisition using tango device servers
# v1.7 12/9/2019
# Juan de la Figuera juan.delafiguera@gmail.com

from datetime import date
import tango
import os
#import numpy
import time

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
        if step > 0 and start > stop+ step:
            break
        elif step < 0 and start < stop+ step:
            break
        yield ("%g" % start) # return float number
        start = start + step
#end of function frange()


counter_filename="//hematite.labo/superficies/LEEM_Madrid/macros.dat"

leem2k=tango.DeviceProxy("leem/measurement/LEEM2k")
uview=tango.DeviceProxy("leem/measurement/Uview")
position=tango.DeviceProxy("leem/measurement/positionXY")
name="000"

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
    else:
        print("Directory "+dayname+" already exists")
    f=open(counter_filename,"w")
    f.write(prefix+","+dayfolder+",0")
    f.close()

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
                savename=expname+"_%03d"%a
                if (uview.SaveImageAsDAT(full+"/"+savename)=="0"):
                    print "Saved %s"%savename
                a+=1
                time.sleep(delay)
        else:
            for a in range(n):
                savename=expname+"_%03d"%a
                if (uview.SaveImageAsDAT(full+"/"+savename)=="0"):
                    print "Saved %s"%savename
                time.sleep(delay)
    except KeyboardInterrupt:
        print "Ok, so you want to finish. Let me clean up."
    uview.ContinousAcquisition=True
    uview.Exposure=oldExposure
    uview.Average=oldAverage

def leemIV(E0,Ef,dE,exp=400.0,avg=0,repeat=False):
    """ leemIV (Initial Energy (V), Final Energy (V), increment E (V), exposure (ms), average,
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
    try:
        while (True):
            a=0
            for i in e:
                leem2k.StartVoltage=float(i)
                print "Image %d Energy %f"%(a,float(i))
                f.write("%d %f\n"%(a,float(i)))
                uview.AcquireSingleImage()
                while (uview.AcquisitionInProgress):
                    pass
                savename=expname+"_%03d"%a
                if (uview.SaveImageAsDAT(full+"/"+savename)=="0"):
                    print "Saved %s"%savename
                a+=1
            if (repeat==False):
                break
    except KeboardInterrupt:
        print "Ok, ok, stopping adquisition. Let me clean up"
    f.close()
    uview.ContinousAcquisition=True
    uview.Exposure=oldExposure
    uview.Average=oldAverage


def leemIV_ROI(E0,Ef,dE,exp=400.0,avg=0,repeat=False):
    """ leemIV (Initial Energy (V), Final Energy (V), increment E (V), exposure (ms), average,
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
    f.write("# Image number  Energy (eV) ROI1 (arb.u.)\n")
    e=frange(E0,Ef,dE)
    try:
        while (True):
            a=0
            for i in e:
                leem2k.StartVoltage=float(i)
                uview.AcquireSingleImage()
                while (uview.AcquisitionInProgress):
                    pass
                print "Image %d Energy %f ROI1 %f"%(a,float(i),float(uview.IntensityROI1))
                f.write("%d %f %f\n"%(a,float(i),float(uview.IntensityROI1)))
                a+=1
            if (repeat==False):
                break
    except KeboardInterrupt:
        print "Ok, ok, you want me to stop. Cleaning up"

    f.close()
    uview.ContinousAcquisition=True
    uview.Exposure=oldExposure
    uview.Average=oldAverage


def leemIVandObj(E0,Ef,dE,startObj,endObj, exp=400.0,avg=0):
    """ leemIV (Initial Energy (V), Final Energy (V), increment E (V), Start Objective (mA), End Objective (mA), exposure (ms), average,
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
        savename=expname+"_%03d"%a
        if (uview.SaveImageAsDAT(full+"/"+savename)=="0"):
            print "Saved %s"%savename
        a+=1
    f.close()
    uview.ContinousAcquisition=True
    uview.Exposure=oldExposure
    uview.Average=oldAverage
