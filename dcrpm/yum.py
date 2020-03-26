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
import signal
import time

from . import pidutil
from .util import (
    DBNeedsRebuild,
    DcRPMException,
    RepairAction,
    read_os_name,
    run_with_timeout,
    which,
)


YUM_PID_PATH = "/var/run/yum.pid"  # type: str
YUM_TIMEOUT_SEC = 30  # type: int
# 6 hours
MIN_YUM_AGE = 3600 * 6  # type: int
YUM_CMD_NAME = "yum"  # type: str
DNF_CMD_NAME = "dnf"  # type: str
KILL_TIMEOUT = 5  # type: int


class Yum:
    def __init__(self):
        # type: () -> None
        self.logger = logging.getLogger()  # type: logging.Logger
        self.status_logger = logging.getLogger("status")  # type: logging.Logger
        self.yum = YUM_CMD_NAME  # type: str
        try:
            which(self.yum)
        except DcRPMException:
            try:
                self.yum = DNF_CMD_NAME
                which(self.yum)
            except DcRPMException:
                self.yum = YUM_CMD_NAME
                m = "Neither yum nor dnf was found!"
                if read_os_name() == "Darwin":
                    self.logger.warning(m)
                else:
                    raise DcRPMException(m)

        self.logger.info("Using %s for yum" % self.yum)

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
        if name != self.yum:
            msg = "Found wrong command name [{}], expecting {}".format(name, self.yum)
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
            run_with_timeout([self.yum, "clean", "expire-cache"], YUM_TIMEOUT_SEC)
        except DcRPMException:
            raise DBNeedsRebuild

    def run_yum_check(self):
        # type: () -> None
        """
        Run yum check - which "Checks for problems in the rpmdb"
        """
        try:
            run_with_timeout([self.yum, "check"], YUM_TIMEOUT_SEC)
        except DcRPMException:
            raise DBNeedsRebuild
