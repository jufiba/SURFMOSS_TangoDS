# -*- coding: utf-8 -*-
#
# This file is part of the LeyboldIG3 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""LeyboldIG3

Server to use remotely the Leybold IG3 Gauge Electronics.
"""

from . import release
from .LeyboldIG3 import LeyboldIG3, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
