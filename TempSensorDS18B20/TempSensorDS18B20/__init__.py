# -*- coding: utf-8 -*-
#
# This file is part of the TempSensorDS18B20 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""TempSensorDS18B20

Device server to read the temperature in a Raspberry PI with a DS18B20 sensor.

It needs (if using GPIO pin 4):
- the w1_gpio,w1_therm modules in /etc/modules
- set dtoverlay=w1-gpio,gpiopin=4 in /boot/config.txt&
- python3-w1termsensor module
"""

from . import release
from .TempSensorDS18B20 import TempSensorDS18B20, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
