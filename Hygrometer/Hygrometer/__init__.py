# -*- coding: utf-8 -*-
#
# This file is part of the Hygrometer project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""Hydrometer

DS for reading the data from an Arduino connected to YL-69/YL-38 sensors.
"""

from . import release
from .Hygrometer import Hygrometer, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
