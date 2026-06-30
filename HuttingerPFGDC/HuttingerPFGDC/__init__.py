# -*- coding: utf-8 -*-
#
# This file is part of the HuttingerPFGDC project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""HuttingerPFGDC

Driver for the Huttinger DC generators, such as the PFG-DC1500, a 1500W 1KV power supply for magnetron sputtering growth.
"""

from . import release
from .HuttingerPFGDC import HuttingerPFGDC, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
