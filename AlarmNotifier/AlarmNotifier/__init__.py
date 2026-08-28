# -*- coding: utf-8 -*-
#
# This file is part of the AlarmNotifier project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""AlarmNotifier

Watches the State of other device servers and sends e-mail.
"""

from . import release
from .AlarmNotifier import AlarmNotifier, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
