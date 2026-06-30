# -*- coding: utf-8 -*-
#
# This file is part of the HuttingerPFGRF project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""HuttingerPFGRF

Driver for the Huttinger RF generators, such as the PFG-RF300 a power supply for magnetron sputtering growth.
"""

from . import release
from .HuttingerPFGRF import HuttingerPFGRF, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
