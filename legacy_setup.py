#!/usr/bin/env python
#
# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the GPLv2 license found in the LICENSE
# file in the root directory of this source tree.
#

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import sys

from setuptools import setup, find_packages

import dcrpm.__version__

if sys.version_info.major < 3 or (
    sys.version_info.major == 3 and sys.version_info.minor < 6
):
    tests_require = ["mock", "typing"]
else:
    tests_require = []

tests_require.append("TestSlide")

setup(
    name="dcrpm",
    version=dcrpm.__version__,
    packages=find_packages(exclude=["tests"]),
    author="Sean Karlage",
    author_email="skarlage@fb.com",
    url="https://github.com/facebookincubator/dcrpm",
    classifiers=[
        "Operating System :: POSIX :: Linux",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Development Status :: 3 - Alpha",
        "Topic :: Utilities",
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
    ],
    keywords=["dcrpm", "dnf", "rpm", "yum", "db_recover", "db4", "bdb"],
    description="A tool to detect and correct common issues around RPM database corruption.",
    long_description=open("README.md", "r").read(),
    long_description_content_type="text/markdown",
    license="GPLv2",
    install_requires=["psutil"],
    tests_require=tests_require,
    test_suite="tests",
    entry_points={"console_scripts": ["dcrpm=dcrpm.main:main"]},
)
