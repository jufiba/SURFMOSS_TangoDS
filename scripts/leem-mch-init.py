#!/usr/bin/python3

# Re-init LEEM MCH gauge device server
# 14/9/2021
# Juan de la Figuera

import tango
import time
import os
import sys
import signal

gmch=tango.DeviceProxy("leem/vacuum/gaugeMCH")

def handle_exit(sig, frame):
    raise(SystemExit)

pid = str(os.getpid())
pidfile = "/tmp/leem-mch-init.pid"

if os.path.isfile(pidfile):
    print("%s already exists, exiting" % pidfile)
    sys.exit()
    
f=open(pidfile, 'w')
f.write(pid)
f.close()

signal.signal(signal.SIGTERM, handle_exit)
try:
    while (1):
        gmch.init()
        time.sleep(120)
except:
    os.unlink(pidfile)
    print("Exiting cleanly")

    
