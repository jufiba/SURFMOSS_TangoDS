#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the GammaVacuumSPCe project
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

import os
import sys
from setuptools import setup

setup_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, setup_dir)

readme_filename = os.path.join(setup_dir, 'README.rst')
with open(readme_filename) as f:
    long_description = f.read()

release_filename = os.path.join(setup_dir, 'GammaVacuumSPCe', 'release.py')
exec(open(release_filename).read())

setup(
    name=name,
    version=version,
    description=description,
    packages=['GammaVacuumSPCe'],
    include_package_data=True,
    install_requires=['pytango'],
    entry_points={'console_scripts': ['GammaVacuumSPCe = GammaVacuumSPCe:main']},
    author=author,
    author_email=author_email,
    license=license,
    long_description=long_description,
    url=url,
    platforms="All Platforms",
)
