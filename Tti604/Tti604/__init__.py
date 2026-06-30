# -*- coding: utf-8 -*-
#
# This file is part of the Tti604 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""tti604

Device to use the RS TTI 604 DVMM. It has a rather horrible interface.
"""

from . import release
from .Tti604 import Tti604, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
