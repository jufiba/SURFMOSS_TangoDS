# -*- coding: utf-8 -*-
#
# This file is part of the AMLPGC1 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""AMLPGC1

Device server for AML PGC1.
"""

from . import release
from .AMLPGC1 import AMLPGC1, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
