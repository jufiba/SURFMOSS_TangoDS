# -*- coding: utf-8 -*-
#
# This file is part of the ElmitecLEEM2k project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""ElmitecLEEM2k

Device server for accessing the settings of the LEEM2000 program from Elmitec.
"""

from . import release
from .ElmitecLEEM2k import ElmitecLEEM2k, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
