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

counter_filename="/home/surfmoss/macros.dat"

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


gauge=tango.DeviceProxy("sputtering/vacuum/gauge")
mfcAr=tango.DeviceProxy("sputtering/vacuum/mfc_Ar")
mfcO2=tango.DeviceProxy("sputtering/vacuum/mfc_O2")
#magRFmag=tango.DeviceProxy("sputtering/magnetron/rfmag")
dummy=0.0
(full,name)=sputt_makenextfolder_and_inc()

f=open(full+"/log.txt","w")
try:
  a=0
  title="time pressure mfc_Ar mfc_O2 RFmag"
  f.write(title+"\n")
  print(title)
  while (1):
     t=time.localtime()
     timenow=time.strftime("%D:%H:%M:%S", t)
     data="%s %3.1e %5.2f %5.2f %5.2f"%(timenow,gauge.Pressure,mfcAr.Measure,mfcO2.Measure,dummy)
     f.write(data+"\n")
     print(data)
     f.flush()
     time.sleep(10)
except KeyboardInterrupt:
   print "Ok, so you want to finish. Let me clean up."
   f.close()
