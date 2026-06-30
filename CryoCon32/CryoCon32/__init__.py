# -*- coding: utf-8 -*-
#
# This file is part of the CryoCon32 project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""CryoCon 32 device server

Minimalistic driver for the Cryocon32 controller used in our Mossbauer transmission setup.
"""

from . import release
from .CryoCon32 import CryoCon32, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
