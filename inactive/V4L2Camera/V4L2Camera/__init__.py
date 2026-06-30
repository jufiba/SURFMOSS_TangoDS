# -*- coding: utf-8 -*-
#
# This file is part of the V4L2Camera project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""V4L2Camera

A simple driver to obtain frames from a V4L2 Camera.
"""

from . import release
from .V4L2Camera import V4L2Camera, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
