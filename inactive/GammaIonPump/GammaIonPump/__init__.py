# -*- coding: utf-8 -*-
#
# This file is part of the GammaIonPump project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""GammaIonPump

Simple controller for running the Gamma Vacuum Ion Pump Controllers.
"""

from . import release
from .GammaIonPump import GammaIonPump, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
