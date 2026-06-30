# -*- coding: utf-8 -*-
#
# This file is part of the TempSensorDS18B20 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""Release information for Python Package"""

name = """tangods-tempsensords18b20"""
version = "1.0.0"
version_info = version.split(".")
description = """Device server to read the temperature in a Raspberry PI with a DS18B20 sensor.

It needs (if using GPIO pin 4):
- the w1_gpio,w1_therm modules in /etc/modules
- set dtoverlay=w1-gpio,gpiopin=4 in /boot/config.txt&
- python3-w1termsensor module"""
author = "juan.delafiguera"
author_email = "juan.delafiguera at gmail.com"
license = """GPL"""
url = """www.tango-controls.org"""
copyright = """"""
