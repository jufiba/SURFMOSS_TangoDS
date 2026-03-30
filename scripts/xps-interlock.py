#!/usr/bin/python3

# Interlock of SPECS x-ray gun
# 18/03/2021
# Juan de la Figuera

import tango
import time
import os
import sys
import signal

switch=tango.DeviceProxy("xps/safety/xrayguninterlock")
water=tango.DeviceProxy("xps/safety/water")

def handle_exit(sig, frame):
    raise(SystemExit)

pid = str(os.getpid())
pidfile = "/tmp/xps-interlock.pid"

if os.path.isfile(pidfile):
    print("%s already exists, exiting" % pidfile)
    sys.exit()
    
f=open(pidfile, 'w')
f.write(pid)
f.close()

signal.signal(signal.SIGTERM, handle_exit)
try:
    while (1):
        if (water.channel0>2.5):
            switch.On()
        else:
            switch.Off()
        time.sleep(1)
except:
    os.unlink(pidfile)
    print("Exiting cleanly")
    switch.Off()

    
