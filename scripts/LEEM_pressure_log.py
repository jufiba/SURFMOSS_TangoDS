#!/usr/bin/python3

# Script for saving the pressure in the LEEM. To be launched from a cron job at some stupid time.
# 08/12/2020
# Juan de la Figuera

import tango
import datetime

now = datetime.datetime.now()

gaugeMCH=tango.DeviceProxy("leem/vacuum/gaugeMCH")
gaugePCH=tango.DeviceProxy("leem/vacuum/gaugePCH")

filename="/home/juan/miNube/labo/LEEM_Madrid_presssure.log"

f=open(filename,"a")

p_mch=float(gaugeMCH.Pressure_IG1)
p_col=float(gaugeMCH.Pressure_IG2)
p_pch=float(gaugePCH.Pressure)

f.write("%s %7.1e %7.1e %7.1e\n"%(now.strftime("%Y/%m/%d %H:%M:%S"),p_mch,p_col,p_pch))

f.close()

