# -*- coding: utf-8 -*-
#
# This file is part of the Itech6000C project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""Itech6000C

ITech6000C control through ethernet socket.
"""

from . import release
from .Itech6000C import Itech6000C, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
