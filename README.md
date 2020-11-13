# SURFMOSS_TangoDS
This are various Device Servers for the Tango Control system to interface with hardware we have in our laboratory. A lot of it is connected by RS232 serial ports through USB converters, and also quite a few are connected to Arduinos. The quality varies a lot. As we are a small lab, we have not worried too much about complete error checking, if something dies usually we drop by and restart the software. Also, most of it is written in Python, using the tango Python HL interface for device servers, and using Pogo.

In the repository we only keep the Pogo XMI file, and the python file corresponding to the Pogo file. In order to install a given device server, run:

cd folder_of_device_server

run "pogo device_server.xmi" 

Inside pogo, select "File->Generate" (marking the "Python package" option before clickin ok).

from the CLI, "python setup.py install" (be careful to use either python2 or python3 depending on the particular device server).

