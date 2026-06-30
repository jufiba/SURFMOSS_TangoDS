# -*- coding: utf-8 -*-
#
# This file is part of the ArduinoDAC project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""ArduinoDAC

Server for a simple interface of an Arduino connected to a DAC
"""

from . import release
from .ArduinoDAC import ArduinoDAC, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
