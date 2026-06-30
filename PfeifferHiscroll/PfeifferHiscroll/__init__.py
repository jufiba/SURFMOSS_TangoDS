# -*- coding: utf-8 -*-
#
# This file is part of the PfeifferHiscroll project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""PfeifferHiscroll

This is a server that provides the same funcionality as the Pfeiffer DCU display unit.
"""

from . import release
from .PfeifferHiscroll import PfeifferHiscroll, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
