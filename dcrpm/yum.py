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
import signal
import time

from . import pidutil
from .util import DBNeedsRebuild, DcRPMException, RepairAction, run_with_timeout


YUM_PID_PATH = "/var/run/yum.pid"
YUM_TIMEOUT_SEC = 30
MIN_YUM_AGE = 3600 * 6  # 6 hours
YUM_CMD_NAME = "yum"
KILL_TIMEOUT = 5  # seconds


class Yum:
    def __init__(self):
        # type: () -> None
        self.logger = logging.getLogger()
        self.status_logger = logging.getLogger("status")

    def check_stuck(self, dry_run=False):
        # type: (bool) -> bool
        try:
            pid, mtime = pidutil.pidfile_info(YUM_PID_PATH)

        # Fine if there's no pidfile, means nothing is using yum.
        except IOError:
            self.logger.info("No yum pid found. Assuming yum not stuck.")
            return True
        except ValueError:
            self.logger.info("Invalid pid value")
            return False
        except Exception:
            self.logger.error("Cannot read %s", YUM_PID_PATH)
            return False

        # Check whether yum.pid mtime is new enough.
        age = int(time.time()) - mtime
        if age < MIN_YUM_AGE:
            self.logger.info("Found yum.pid, but is only %ds old", age)
            return True

        # Check what command corresponds to yum.pid.
        proc = pidutil.process(pid)
        if not proc:
            self.status_logger.warning("Failed to get command name")
            return False
        name = proc.name()
        if name != YUM_CMD_NAME:
            msg = "Found wrong command name [{}], expecting {}".format(
                name, YUM_CMD_NAME
            )
            self.status_logger.warning(msg)
            self.logger.error(msg)
            return False

        self.logger.info("Got: pid=%d, mtime=%d, cmdname=%s", pid, mtime, name)
        if dry_run:
            self.logger.info("Dry-run mode; would have killed pid %d", pid)
            return True

        self.logger.info("Killing pid %d", pid)
        if not pidutil.send_signal(proc, signal.SIGKILL, timeout=KILL_TIMEOUT):
            self.status_logger.warning("kill failed")
            return False

        self.status_logger.warning(RepairAction.STUCK_YUM)
        return True

    def run_yum_clean(self):
        # type: () -> None
        """
        Run yum clean expire-cache, which we've seen failing when rpmdb indexes
        were busted
        """
        try:
            cmd = "{} clean expire-cache".format(YUM_CMD_NAME)
            run_with_timeout(cmd, YUM_TIMEOUT_SEC)
        except DcRPMException:
            raise DBNeedsRebuild

    def run_yum_check(self):
        # type: () -> None
        """
        Run yum check - which "Checks for problems in the rpmdb"
        """
        try:
            cmd = "{} check".format(YUM_CMD_NAME)
            run_with_timeout(cmd, YUM_TIMEOUT_SEC)
        except DcRPMException:
            raise DBNeedsRebuild
