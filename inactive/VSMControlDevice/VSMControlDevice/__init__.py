# -*- coding: utf-8 -*-
#
# This file is part of the VSMControlDevice project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""VSM Control Device

Reading data and generation of images in hysteresis cycles
"""

from . import release
from .VSMControlDevice import VSMControlDevice, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
