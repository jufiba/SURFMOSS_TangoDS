#!/usr/bin/python3

# VSM script for making a complete loop starting at the maximum
# 15/04/2019
# Juan de la Figuera

import tango
import time
import sys
import numpy
import matplotlib
import scipy
import matplotlib.pyplot as plt

iobox=tango.DeviceProxy("vsm/measurement/iobox")
polarity=tango.DeviceProxy("vsm/measurement/Polarity")
mag=tango.DeviceProxy("vsm/measurement/magnetic_field")
magnet=tango.DeviceProxy("vsm/measurement/magnet")

# Input parameters
if (len(sys.argv)<4):
	print("vsm max_current(A) delta_current(A) delta_t(s) Filename (optional, output.dat otherwise) Comment (in quotes)\n return_to_zero_end(True/False)")
	exit()

max_current=float(sys.argv[1])
delta_current=float(sys.argv[2])
delta_t=float(sys.argv[3])


if (len(sys.argv)>3):
    filename=sys.argv[4]
else:
    filename="output.dat"
    comment="None"
    return_to_zero_end=True
if (len(sys.argv)>4):
    comment=sys.argv[5]
    return_to_zero_end=True
else:
    comment="None"
    return_to_zero_end=True
if (len(sys.argv)>6):
    if (sys.argv[6]=="True"):
        return_to_zero_end=True
    else:
        return_to_zero_end=False
    

n=int(max_current/delta_current)
data=numpy.zeros((4*n,3),float)


plt.axis([-max_current,max_current, -10, 10])
plt.title(filename+" "+comment)
plt.xlabel("Current (A)")
plt.ylabel("Locking Output (V)")
print("Filename %s Comment %s"%(filename,comment))
print("Max Current %4.2f A Steps %i Time %4.2f\n"%(max_current,n,delta_t))

#Start cycle
index=0
for i in range(n,0,-1):
	print("vuelta pos %d"%i)
	current=i*delta_current
	magnet.Output=current
	time.sleep(delta_t)
	mu=iobox.ADC0
	b=mag.Field
	data[index,0]=current
	data[index,1]=b
	data[index,2]=mu
	plt.scatter(current,mu,color="b",marker=".")
	plt.pause(0.05)
	index+=1

magnet.Output=0.0
polarity.setNegative()
time.sleep(5)

for i in range(0,n):
	print("ida neg %d"%i)
	current=i*delta_current
	magnet.Output=current
	time.sleep(delta_t)
	mu=iobox.ADC0
	b=mag.Field
	data[index,0]=-current
	data[index,1]=b
	data[index,2]=mu
	plt.scatter(-current,mu,color="b",marker=".")
	plt.pause(0.05)
	index+=1

for i in range(n,0,-1):
	print("vuelta neg %d"%i)
	current=i*delta_current
	magnet.Output=current
	time.sleep(delta_t)
	mu=iobox.ADC0
	b=mag.Field
	data[index,0]=-current
	data[index,1]=b
	data[index,2]=mu
	plt.scatter(-current,mu,color="r",marker=".")
	plt.pause(0.05)
	index+=1

magnet.Output=0.0
polarity.setPositive()
time.sleep(5)

for i in range(0,n):
	print("ida pos %d"%i)
	current=i*delta_current
	magnet.Output=current
	time.sleep(delta_t)
	mu=iobox.ADC0
	b=mag.Field
	data[index,0]=current
	data[index,1]=b
	data[index,2]=mu
	plt.scatter(current,mu,color="r",marker=".")
	plt.pause(0.05)
	index+=1


# Save stuff
scipy.savetxt(filename,data,header=comment)
plt.clf()
plt.plot(data[:int(len(data)/2),1],data[:int(len(data)/2),2],color="b",marker=".")
plt.plot(data[int(len(data)/2):,1],data[int(len(data)/2):,2],color="r",marker=".")
plt.title(filename+" "+comment)
plt.xlabel("Magnetic Field (T)")
plt.ylabel("Magnetization (arb. units)")
plt.savefig(filename+".png")
plt.savefig(filename+".pdf")

if (return_to_zero_end):
    for i in range(n,0,-1):
        print("vuelta pos %d"%i)
        current=i*delta_current
        magnet.Output=current
        time.sleep(delta_t)

exit()
