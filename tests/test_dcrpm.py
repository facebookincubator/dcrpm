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

import argparse
import os
import typing as t
from os.path import join

import testslide
from dcrpm import dcrpm, pidutil, rpmutil, util


try:
    from unittest.mock import MagicMock, patch
except ImportError:
    from mock import MagicMock, patch


statvfs_result = t.NamedTuple("statvfs_result", [("f_bsize", int), ("f_bfree", int)])


class TestDcRPM(testslide.TestCase):
    def setUp(self):
        # type: () -> None
        super(TestDcRPM, self).setUp()
        self.rpm_path = util.which("rpm")  # type: str
        self.dbpath = "/var/lib/rpm"  # type: str
        self.recover_path = util.which("db_recover")  # type: str
        self.verify_path = util.which("db_verify")  # type: str
        self.stat_path = util.which("db_stat")  # type: str
        self.yum_complete_transaction_path = (
            "/usr/bin/yum-complete-transaction"
        )  # type: str
        self.blacklist = ["table1", "table2"]  # type: t.List[str]
        self.rpmutil = rpmutil.RPMUtil(
            dbpath=self.dbpath,
            rpm_path=self.rpm_path,
            recover_path=self.recover_path,
            verify_path=self.verify_path,
            stat_path=self.stat_path,
            yum_complete_transaction_path=self.yum_complete_transaction_path,
            blacklist=self.blacklist,
            forensic=False,
        )  # type: rpmutil.RPMUtil
        self.rpmutil.tables = ["table0", "table1", "table2", "table3"]

        # Args
        self.args = argparse.Namespace(
            dry_run=False,
            check_stuck_yum=True,
            rpm_path=self.rpm_path,
            recover_path=self.recover_path,
            verify_path=self.verify_path,
            stat_path=self.stat_path,
            clean_yum_transactions=False,
            yum_complete_transaction_path=self.yum_complete_transaction_path,
            dbpath=self.dbpath,
            run_yum_clean=False,
            run_yum_check=False,
            max_passes=5,
            minspace=150 * 1048576,
            verbose=False,
            logfile="/var/log/blah.log",
            blacklist=["table2", "table3"],
            forensic=False,
        )  # type: argparse.Namespace

        # DcRPM
        self.dcrpm = dcrpm.DcRPM(self.rpmutil, self.args)  # type: dcrpm.DcRPM

    # run_recovery
    def test_run_recovery_dry_run(self):
        # type: () -> None
        self.mock_callable(pidutil, "send_signals").and_assert_not_called()
        self.mock_callable(self.rpmutil, "recover_db").and_assert_not_called()
        self.args.dry_run = True
        self.dcrpm.run_recovery()

    # db_stat
    def test_db_stat_forensic(self):
        # type: () -> None
        self.mock_callable(pidutil, "send_signals").and_assert_not_called()
        (
            self.mock_callable(self.rpmutil, "db_stat")
            .to_return_value(None)
            .and_assert_called()
        )
        self.args.forensic = True
        self.args.dry_run = True
        self.dcrpm.run()

    # run_rebuild
    def test_run_rebuild_dry_run(self):
        # type: () -> None
        self.mock_callable(self.rpmutil, "rebuild_db").and_assert_not_called()
        self.args.dry_run = True
        self.dcrpm.run_rebuild()

    # hardlink_db001
    def test_hardlink_db001_link_exists(self):
        # type: () -> None
        old = join(self.dbpath, "__db.001")
        new = join(self.dbpath, "__dcrpm_py_inode_pointer")
        (
            self.mock_callable(os, "unlink")
            .for_call(new)
            .to_raise(OSError())
            .and_assert_called_once()
        )
        (
            self.mock_callable(os, "link")
            .for_call(old, new)
            .to_return_value(None)
            .and_assert_called_once()
        )
        p = self.dcrpm.hardlink_db001()
        self.assertEqual(p, new)

    def test_hardlink_db001_symlink_fails(self):
        # type: () -> None
        old = join(self.dbpath, "__db.001")
        new = join(self.dbpath, "__dcrpm_py_inode_pointer")
        (
            self.mock_callable(os, "unlink")
            .for_call(new)
            .to_return_value(None)
            .and_assert_called_once()
        )
        (
            self.mock_callable(os, "link")
            .for_call(old, new)
            .to_raise(OSError())
            .and_assert_called_once()
        )
        with self.assertRaises(util.DcRPMException):
            self.dcrpm.hardlink_db001()

    # stale_yum_transactions_exist
    def test_stale_yum_transactions_no_exist(self):
        # type: () -> None
        yum_path = dcrpm.DcRPM.YUM_PATH
        (
            self.mock_callable(os, "listdir")
            .for_call(yum_path)
            .to_yield_values(
                [
                    join(yum_path, "file1"),
                    join(yum_path, "file2"),
                    join(yum_path, "file3"),
                ]
            )
            .and_assert_called_once()
        )
        self.assertFalse(self.dcrpm.stale_yum_transactions_exist())

    def test_stale_yum_transactions_exist(self):
        # type: () -> None
        yum_path = dcrpm.DcRPM.YUM_PATH
        (
            self.mock_callable(os, "listdir")
            .for_call(yum_path)
            .to_yield_values(
                [
                    join(yum_path, "file1"),
                    join(yum_path, "transaction-all.5"),
                    join(yum_path, "file3"),
                ]
            )
            .and_assert_called_once()
        )
        self.assertTrue(self.dcrpm.stale_yum_transactions_exist())

    # has_free_disk_space
    def test_has_free_disk_space_success(self):
        # type: () -> None
        (
            self.mock_callable(os, "statvfs")
            .for_call(self.dbpath)
            .to_return_value(statvfs_result(4096, 108710048))
        )
        self.assertTrue(self.dcrpm.has_free_disk_space())

    def test_has_free_disk_space_fail(self):
        # type: () -> None
        (
            self.mock_callable(os, "statvfs")
            .for_call(self.dbpath)
            .to_return_value(statvfs_result(4096, 5))
        )
        self.assertFalse(self.dcrpm.has_free_disk_space())
