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

from fnmatch import fnmatch
import logging
import os
from os.path import join
import signal

from . import pidutil
from .stuckyum import StuckYum
from .util import (
    DBNeedsRecovery,
    DBNeedsRebuild,
    DcRPMException,
    RepairAction,
)


class DcRPM:
    YUM_PATH = '/var/lib/yum'
    YUM_TRANSACTION_BASE = '**/*transaction-all.*'

    def __init__(self, rpmutil, args):
        # type: (RPMUtil, argparse.Namespace) -> None
        self.rpmutil = rpmutil
        self.args = args
        self.logger = logging.getLogger()
        self.status_logger = logging.getLogger('status')

    def run(self):
        # type: () -> bool
        if not self.has_free_disk_space():
            self.status_logger.error('not_enough_disk')
            self.logger.error(
                'Need at least %sB free to continue' % self.args.minspace
            )
            return False

        # Check old yum transactions.
        if self.args.clean_yum_transactions and self.stale_yum_transactions_exist():
            self.logger.info('Cleaning old yum transaction')
            self.rpmutil.clean_yum_transactions()

        # Check stuck yum.
        if self.args.check_stuck_yum:
            result = StuckYum().run(dry_run=self.args.dry_run)
            if not result:
                self.logger.error('StuckYum check failed')

        # Start main checks.
        for i in range(self.args.max_passes):
            self.logger.debug('Running pass: %d', i)

            try:
                # Black box check - does rpm -qa even work?
                self.logger.info('Running black box check (rpm -qa)')
                self.rpmutil.check_rpm_qa()
                self.logger.info('Black box check OK')

                # Check tables (mismatch for -qa vs. -q).
                self.logger.info(
                    'Running table checks (attempting to query each package)'
                )
                self.rpmutil.check_tables()
                self.logger.info('Table checks OK')

                # Verify tables (db_verify for each file).
                self.logger.info('Verifying each table in %s', self.args.dbpath)
                if not self.call_verify_tables():
                    continue

            # Need to run db_recover.
            except DBNeedsRecovery:
                self.logger.error('DB needs recovery')
                self.run_recovery()
                continue

            # Need to run rpm --rebuilddb.
            except DBNeedsRebuild:
                self.logger.error('DB needs rebuild')
                self.run_rebuild()
                continue

            # Everything else.
            except DcRPMException as e:
                self.logger.warning('Got other exception: %s', e)
                continue

            # All's well - return early!
            self.logger.info(
                'Ran a pass without detecting any problems. Exiting.'
            )
            return True

        # Ran out of attempts.
        self.status_logger.error('')
        self.logger.error('Unable to repair RPM database')
        return False

    def run_recovery(self):
        # type: () -> None
        """
        Performs DB recovery by doing the following:
            * Kills pids holding the .dbenv.lock file
            * Hardlinks the __db.001 file (since db_recovery blows it away)
            * Runs db_recovery
        """
        self.status_logger.info(RepairAction.DB_RECOVERY)
        if self.args.dry_run:
            self.logger.info(
                '[dry-run] RPM DB at %s needs recovery',
                self.args.dbpath,
            )
            return

        # Copied from the original C++ dcrpm:
        # Starting with RHEL/CentOS 7, this file might be held open, and it
        # seems to take precedence over __db.001.  So, try cleaning that up
        # first.  If this actually kills someone, stop recovery here, since
        # many times, the other users will wake up and finish.
        self.logger.info('Attempting to fix RPM DB at %s', self.args.dbpath)
        dbenv_lockfile = join(self.args.dbpath, '.dbenv.lock')
        rpm_lockfile = join(self.args.dbpath, '.rpm.lock')
        lock_pids = pidutil.pids_holding_file(dbenv_lockfile)
        lock_pids |= pidutil.pids_holding_file(rpm_lockfile)

        self.logger.debug('Found %d pids holding lock files', len(lock_pids))
        if lock_pids and pidutil.send_signals(lock_pids, signal.SIGKILL):
            self.logger.debug('Killed pids holding lock files')
            self.status_logger.warning('killed_lock_users')
            return

        # Hardlink to __db.001 and kill holders of that file.
        hardlink = self.hardlink_db001()
        pidutil.send_signals(
            pidutil.pids_holding_file(hardlink),
            signal.SIGKILL,
        )
        os.unlink(hardlink)

        # Run the recovery.
        self.rpmutil.recover_db()

    def run_rebuild(self):
        # type: () -> None
        self.status_logger.info(RepairAction.TABLE_REBUILD)
        if self.args.dry_run:
            self.logger.warning(
                '[dry-run] RPM tables at %s needs recovery',
                self.args.dbpath,
            )
            return
        self.rpmutil.rebuild_db()

    def hardlink_db001(self):
        # type: () -> str
        old_path = join(self.args.dbpath, '__db.001')
        new_path = join(self.args.dbpath, '__dcrpm_py_inode_pointer')

        # Make sure it doesn't exist.
        try:
            os.unlink(new_path)
        except OSError:
            pass

        # Then save it.
        try:
            os.link(old_path, new_path)
            return new_path
        except OSError:
            self.status_logger.warning('link_failed')
            raise DcRPMException('Could not save __db.001 failed')

    def stale_yum_transactions_exist(self):
        # type: () -> bool
        """
        Detects whether there are stale yum transactions in /var/lib/yum.
        """
        return any(
            fnmatch(str(f), self.YUM_TRANSACTION_BASE)
            for f in os.listdir(self.YUM_PATH)
        )

    def has_free_disk_space(self):
        # type: () -> bool
        """
        Checks if `fs` has enough free disk space to perform the remaining
        checks.
        """
        buf = os.statvfs(self.args.dbpath)
        desired_free_blocks = self.args.minspace // buf.f_bsize
        return buf.f_bfree > desired_free_blocks

    def call_verify_tables(self):
        # type: () -> bool:
        """
        Because rpmutil.verify_tables requires a different way of exception
        handling (i.e. if a db_verify fails on one of the tables, we might need
        to kill the .dbenv.lock pids before running rpm --rebuilddb), we wrap
        the call with this method.
        """
        try:
            self.rpmutil.verify_tables()
            self.logger.info('Verify tables OK')
            return True
        except DcRPMException:
            # db_verify of one of the tables failed, so recover, then rebuild.
            # Let any other exceptions bubble up as needed to the main run loop.
            # Not great, but matches the original C++ dcrpm.
            self.run_recovery()
            self.run_rebuild()
            return False
