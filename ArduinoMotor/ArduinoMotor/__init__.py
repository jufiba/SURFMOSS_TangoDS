# -*- coding: utf-8 -*-
#
# This file is part of the ArduinoMotor project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""ArduinoMotor

Custom server for an Arduino driving a motor.
"""

from . import release
from .ArduinoMotor import ArduinoMotor, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
