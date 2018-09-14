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
import os
import time
from datetime import datetime


class ForensicLogger(logging.Handler):
    """
    Minimal implementation of special purpose logger
    We're capturing full verbose command output, and writing to timestamped
    files in `logdir`
    """

    def __init__(self, logdir, *args, **kwargs):
        self.logdir = logdir
        super(ForensicLogger, self).__init__(*args, **kwargs)

    def debug(self, record):
        # Check if 'key' was supplied to the logger
        # logger.debug(text, extra={'key': filename})
        if not hasattr(record, "key"):
            return

        with open(
            os.path.join(
                self.logdir,
                "{}.{}.txt".format(
                    record.key,
                    datetime.fromtimestamp(time.time()).strftime("%Y%m%d%H%M%S"),
                ),
            ),
            "w",
        ) as fp:
            fp.write(record.msg)

    def emit(self, record):
        if record.levelno == logging.DEBUG:
            self.debug(record)
