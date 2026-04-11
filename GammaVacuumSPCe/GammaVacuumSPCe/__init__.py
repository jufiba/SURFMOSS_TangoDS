# -*- coding: utf-8 -*-
#
# This file is part of the GammaVacuumSPCe project
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

"""GammaVacuumSPCe

Device server for the Gamma Vacuum DIGITEL SPCe ion pump power supply.
Connects via Ethernet Telnet interface (TCP port 23).
"""

from . import release
from .GammaVacuumSPCe import GammaVacuumSPCe, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
