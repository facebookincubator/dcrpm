#!/usr/bin/env python
#
# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the GPLv2 license found in the LICENSE
# file in the root directory of this source tree.
#
# pyre-strict

from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import os
import time
import typing as t
from datetime import datetime


class ForensicLogger(logging.Handler):
    """
    Minimal implementation of special purpose logger
    We're capturing full verbose command output, and writing to timestamped
    files in `logdir`
    """

    def __init__(self, logdir, level=logging.NOTSET):
        # type: (str, int) -> None
        self.logdir = logdir
        super(ForensicLogger, self).__init__(level=level)

    def debug(self, record):
        # type: (logging.LogRecord) -> None
        # Check if 'key' was supplied to the logger
        # logger.debug(text, extra={'key': filename})
        if not hasattr(record, "key"):
            return

        with open(
            os.path.join(
                self.logdir,
                "{}.{}.txt".format(
                    # pyre-ignore[16]: 'key' gets inserted dynamically by logger.debug.
                    record.key,
                    datetime.fromtimestamp(time.time()).strftime("%Y%m%d%H%M%S"),
                ),
            ),
            "w",
        ) as fp:
            fp.write(record.msg)

    def emit(self, record):
        # type: (logging.LogRecord) -> None
        if record.levelno == logging.DEBUG:
            self.debug(record)
