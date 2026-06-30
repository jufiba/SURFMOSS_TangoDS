# -*- coding: utf-8 -*-
#
# This file is part of the RaspberryButton project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""RaspberryButton

Simple interface to turn on and off a GPIO pin in a Raspberry PI.
"""

from . import release
from .RaspberryButton import RaspberryButton, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
