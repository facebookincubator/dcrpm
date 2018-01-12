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

import logging
import os
from os.path import basename, join

from .util import (
    DBNeedsRebuild,
    DBNeedsRecovery,
    DcRPMException,
    RepairAction,
    run_with_timeout,
)

RPM_CHECK_TIMEOUT_SEC = 5
VERIFY_TIMEOUT_SEC = 5
RECOVER_TIMEOUT_SEC = 90
REBUILD_TIMEOUT_SEC = 300
MIN_ACCEPTABLE_PKG_COUNT = 50
RPM_PATH = '/bin/rpm'


class RPMUtil:
    """
    Wraps operations around Berkeley DB and rpm tables.
    """

    def __init__(
        self,
        dbpath,
        recover_path,
        verify_path,
        yum_complete_transaction_path,
        blacklist,
    ):
        # type: (str, str, str, str, List[str]) -> None
        self.dbpath = dbpath
        self.recover_path = recover_path
        self.verify_path = verify_path
        self.yum_complete_transaction_path = yum_complete_transaction_path
        self.blacklist = blacklist
        self.logger = logging.getLogger()
        self.status_logger = logging.getLogger('status')
        self.tables = [t for t in os.listdir(self.dbpath) if str(t).istitle()]

    def check_rpm_qa(self):
        # type: () -> None
        """
        Runs `rpm -qa` which serves as a good proxy check for whether bdb needs
        recovery.
        """
        try:
            cmd = '{} --dbpath {} -qa'.format(RPM_PATH, self.dbpath)
            result = run_with_timeout(cmd, RPM_CHECK_TIMEOUT_SEC)
        except DcRPMException:
            self.logger.error('rpm -qa failed')
            self.status_logger.warning('initial_db_check_fail')
            raise DBNeedsRecovery()

        packages = result.stdout.strip().split()
        if len(packages) < MIN_ACCEPTABLE_PKG_COUNT:
            self.logger.error(
                'rpm package count seems too low; saw %d, expected at least %d',
                len(packages),
                MIN_ACCEPTABLE_PKG_COUNT,
            )
            raise DBNeedsRecovery()

        self.logger.debug('Package count: %d', len(packages))

    def recover_db(self):
        # type: () -> None
        """
        Runs `db_recover`.
        """
        cmd = '{} -h {}'.format(self.recover_path, self.dbpath)
        try:
            run_with_timeout(cmd, RECOVER_TIMEOUT_SEC)
        except DcRPMException:
            self.status_logger.warning('db_recover_failed')
            raise

    def rebuild_db(self):
        # type: () -> None
        """
        Runs `rpm --rebuilddb`.
        """
        cmd = '{} --dbpath {} --rebuilddb'.format(RPM_PATH, self.dbpath)
        try:
            run_with_timeout(cmd, REBUILD_TIMEOUT_SEC)
        except DcRPMException:
            self.status_logger.warning('rebuild_tables_failed')
            raise

    def check_tables(self):
        # type: () -> None
        """
        Runs the following:

          `rpm -qa --qf | sort | uniq | xargs rpm -q | grep 'is not installed$'`

        which checks each rpm in the DB to see if there are inconsistencies
        between what rpm thinks is installed and what is in the DB.
        """
        cmd = (
            "{rpm} --dbpath {db} -qa --qf '%{NAME}\\n' | sort | uniq | "
            "xargs {rpm} --dbpath {db} -q | grep 'is not installed$'"
        ).format(
            rpm=RPM_PATH, db=self.dbpath, NAME='NAME'
        )

        try:
            result = run_with_timeout(
                cmd,
                timeout=RPM_CHECK_TIMEOUT_SEC,
                raise_on_nonzero=False,
            )
        except DcRPMException:
            self.status_logger.warning('initial_table_check_fail')
            raise

        # Grep exit code 1 indicates it didn't find bad condition.
        if result.returncode == 0:
            raise DBNeedsRebuild()

    def verify_tables(self):
        # type: () -> None
        """
        Runs `db_verify` on all rpmdb tables.
        """
        for table in self.tables:
            if basename(table) in self.blacklist:
                self.logger.warning("Skipping table '%s', blacklisted", table)
                continue

            cmd = '{} {}'.format(self.verify_path, join(self.dbpath, table))
            try:
                result = run_with_timeout(
                    cmd,
                    VERIFY_TIMEOUT_SEC,
                    raise_on_nonzero=False,
                )
            except DcRPMException:
                self.status_logger.warning('initial_table_verify_fail')
                raise

            # This raises a DcRPMException because it gets handled specially in
            # the main run loop.
            if result.returncode != 0:
                self.logger.error('db_verify returned nonzero status')
                raise DcRPMException()

    def clean_yum_transactions(self):
        # type: () -> None
        """
        Runs yum-complete-transaction.
        """
        cmd = '{} --cleanup'.format(self.yum_complete_transaction_path)
        self.status_logger.info(RepairAction.CLEAN_YUM_TRANSACTIONS)
        run_with_timeout(cmd, RPM_CHECK_TIMEOUT_SEC)
