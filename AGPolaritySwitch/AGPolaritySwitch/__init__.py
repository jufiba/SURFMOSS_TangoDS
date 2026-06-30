# -*- coding: utf-8 -*-
#
# This file is part of the AGPolaritySwitch project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""AGPolaritySwitch

A devicer server for changing the polarity of the high current (up to 30A) power supply. It is a relay box with an Arduino.
"""

from . import release
from .AGPolaritySwitch import AGPolaritySwitch, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
