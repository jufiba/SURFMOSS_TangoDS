# -*- coding: utf-8 -*-
#
# This file is part of the WisselMCA project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""WisselMCA

Device server for the Wissel Multichannel Analyzer used for Mossbauer spectroscopy.
"""

from . import release
from .WisselMCA import WisselMCA, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
