# -*- coding: utf-8 -*-
#
# This file is part of the Keithley2100 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""Keithley2100

Server for Keithley DVMM 61/2 digits
"""

from . import release
from .Keithley2100 import Keithley2100, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
