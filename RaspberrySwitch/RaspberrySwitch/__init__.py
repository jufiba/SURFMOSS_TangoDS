# -*- coding: utf-8 -*-
#
# This file is part of the RaspberrySwitch project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""RaspberrySwitch

Read a switch connected to one of the GPIO pins.
"""

from . import release
from .RaspberrySwitch import RaspberrySwitch, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
