# -*- coding: utf-8 -*-
#
# This file is part of the PfeifferTU400 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""PfeifferTU400

This is a server that provides the same funcionality as the Pfeiffer DCU display unit.
"""

from . import release
from .PfeifferTU400 import PfeifferTU400, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
