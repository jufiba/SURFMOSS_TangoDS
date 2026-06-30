# -*- coding: utf-8 -*-
#
# This file is part of the MKSGauge project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""MKSGauge Reader

This is a very simple reader for the PDR9000 unit with a 972B transducer.
"""

from . import release
from .MKSGauge import MKSGauge, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
