# -*- coding: utf-8 -*-
#
# This file is part of the WaterSwitch project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""

Simple device server to detect wheter water is flowing in a cooling water sensor
"""

from . import release
from .WaterSwitch import WaterSwitch, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
