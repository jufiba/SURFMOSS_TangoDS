# -*- coding: utf-8 -*-
#
# This file is part of the PIDController project
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""PIDController

PID Controller Tango device server
"""

from . import release
from .PIDController import PIDController, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
