# -*- coding: utf-8 -*-
#
# This file is part of the MFC project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""KISS Mass Flow Controller Driver

Simple driver for the Bronkhorst Mass Flow Controllers.
"""

from . import release
from .MFC import MFC, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
