# -*- coding: utf-8 -*-
#
# This file is part of the SEAWaterflowmeter project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""SeaWaterflowmeter

Device server to interface a Raspberry PI using the GPIO to the SEA YF-S201 water flow sensor.
"""

from . import release
from .SEAWaterflowmeter import SEAWaterflowmeter, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
