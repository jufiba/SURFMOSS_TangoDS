# -*- coding: utf-8 -*-
#
# This file is part of the MotorApertura project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""MotorApertura

Stepper driving the LEEM aperture, through an Arduino.
"""

from . import release
from .MotorApertura import MotorApertura, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
