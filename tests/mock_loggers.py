#!/usr/bin/env python
#
# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the GPLv2 license found in the LICENSE
# file in the root directory of this source tree.
#

from __future__ import absolute_import, division, print_function, unicode_literals

import logging

from dcrpm.util import ACTION_NAMES


class NullLogger(logging.Handler):
    """
    Dummy logger for compatibility
    """

    def emit(self, _):
        pass


class TestLogger(logging.Handler):
    """
    Integration test version of status logger
    """

    def __init__(self, *args, **kwargs):
        self.trace = []
        super(TestLogger, self).__init__(*args, **kwargs)

    def emit(self, record):
        if record.msg and record.levelno == logging.INFO:
            self.trace.append(ACTION_NAMES[record.msg])
