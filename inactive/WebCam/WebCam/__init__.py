# -*- coding: utf-8 -*-
#
# This file is part of the WebCam project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""WebCam

A simple device server for a webcam conencted through v4l2, using pygame.
"""

from . import release
from .WebCam import WebCam, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
