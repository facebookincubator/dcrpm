#!/usr/bin/env python
#
# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the GPLv2 license found in the LICENSE
# file in the root directory of this source tree.
#

"""
This is the version file, modify __version__ to update new versions,
then you can import dcrpm.__version__ to get the current one.
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import sys

__version__ = "0.4.0"

sys.modules[__name__] = __version__
