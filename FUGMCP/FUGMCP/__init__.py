# -*- coding: utf-8 -*-
#
# This file is part of the FUGMCP project
#
# GPL 2
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""

Device server for the HV power supply MCP 140-1250 (1250V, 100mA). It has a USB module for digital interfacing, Probus V.
"""

from . import release
from .FUGMCP import FUGMCP, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
