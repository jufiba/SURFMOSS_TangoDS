# -*- coding: utf-8 -*-
#
# This file is part of the MCC1208LS project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""MCC1208LS

Simple interface to the MCC 1208LS usb DAC/ADC box.
"""

from . import release
from .MCC1208LS import MCC1208LS, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
