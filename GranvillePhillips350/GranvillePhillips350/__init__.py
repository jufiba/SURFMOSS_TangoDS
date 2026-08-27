# -*- coding: utf-8 -*-
#
# This file is part of the GranvillePhillips350 project
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""GranvillePhillips350

Device server for the Granville Phillips 350 ion gauge controller, over the
RS-232 interface module.
"""

from . import release
from .GranvillePhillips350 import GranvillePhillips350, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
