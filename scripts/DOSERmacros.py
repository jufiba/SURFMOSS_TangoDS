#!/usr/bin/python
# LEEM Madrid Macros
# Simple MBE doser control using tango device servers
#
# v1.0 28/6/2021 Added doserRampPowerTo. This requires the PID controller to be on, and the gauge of the main chamber working.

# Juan de la Figuera juan.delafiguera@gmail.com

from datetime import date
import tango
import numpy
import time

gaugeMCH=tango.DeviceProxy("leem/vacuum/gaugeMCH")
pid1=tango.DeviceProxy("leem/control/doser_pid")
pid2=tango.DeviceProxy("leem/control/doser2_pid")

def doserRampPowerTo(doser,power,power_step=1.0,time_step=1.0,pressure_limit=1):
    """ doserRampPowerTo (temp, temp_step, time_step, pressure_limit)
    Ramp power using PID (must be on before!)
    Parameters: 
        doser: 1 or 2
        power: final power (in W)
        power_step: temperature change per step (default 1C)
        time_step: waiting time per step (default 1s)
        pressure_limit: if pressure above the limit, will wait (default 1, no limit) """ 
    if (doser==1):
        pid=pid1
    else:
        pid=pid2
    start=pid.SetPoint
    if (start>power):
        r=numpy.arange(start,power,-power_step)
    else:
        r=numpy.arange(start,power,power_step)
    for a in r:
        pid.SetPoint=a
        print("Going to %f"%a)
        while (gaugeMCH.Pressure_IG1 > pressure_limit):
             time.sleep(10)
        time.sleep(time_step)
