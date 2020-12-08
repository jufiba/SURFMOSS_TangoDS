#!/usr/bin/python
# Saving sputtering parameters Macros
# Simple acquisition using tango device servers
#

# Juan de la Figuera juan.delafiguera@gmail.com

from datetime import date
import tango
import os
import numpy
import time

counter_filename="//hematite.labo/superficies/sputtering/macros.dat"

leem2k=tango.DeviceProxy("leem/measurement/LEEM2k")
uview=tango.DeviceProxy("leem/measurement/Uview")
position=tango.DeviceProxy("leem/measurement/positionXY")

def sputt_getfolder():
    if not os.path.exists(counter_filename):
        print "Error, no saved filename"
        exit()
    f=open(counter_filename,"r")
    count=f.readline()
    f.close()
    (prefix,dayfolder,exp)=count.split(",")
    return(prefix,dayfolder,int(exp))

def sputt_makenextfolder_and_inc():
    (prefix,dayfolder,exp)=sputt_getfolder()
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

