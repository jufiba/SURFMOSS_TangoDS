# -*- coding: utf-8 -*-
#
# This file is part of the PfeifferTC100 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""PfeifferTC100

This is a server that provides the same funcionality as the Pfeiffer DCU display unit.
"""

from . import release
from .PfeifferTC100 import PfeifferTC100, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
