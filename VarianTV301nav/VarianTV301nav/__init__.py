# -*- coding: utf-8 -*-
#
# This file is part of the VarianTV301nav project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""Varian TV301NAV

Driver for interfacing with the Varian/Agilent TV301 Navigator pump with integrated controller.
"""

from . import release
from .VarianTV301nav import VarianTV301nav, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
