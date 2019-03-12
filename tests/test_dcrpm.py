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
import typing as t
import unittest
from os.path import join

from dcrpm.dcrpm import DcRPM
from dcrpm.rpmutil import RPMUtil
from dcrpm.util import DcRPMException


try:
    from unittest.mock import MagicMock, patch
except ImportError:
    from mock import MagicMock, patch


statvfs_result = t.NamedTuple("statvfs_result", [("f_bsize", int), ("f_bfree", int)])


class TestDcRPM(unittest.TestCase):
    def setUp(self):
        # type: () -> None
        self.rpm_path = "/usr/bin/rpm"  # type: str
        self.dbpath = "/var/lib/rpm"  # type: str
        self.recover_path = "/usr/bin/db_recover"  # type: str
        self.verify_path = "/usr/bin/db_verify"  # type: str
        self.stat_path = "/usr/bin/db_stat"  # type: str
        self.yum_complete_transaction_path = (
            "/usr/bin/yum-complete-transaction"
        )  # type: str
        self.blacklist = ["table1", "table2"]  # type: t.List[str]
        self.rpmutil = RPMUtil(
            dbpath=self.dbpath,
            rpm_path=self.rpm_path,
            recover_path=self.recover_path,
            verify_path=self.verify_path,
            stat_path=self.stat_path,
            yum_complete_transaction_path=self.yum_complete_transaction_path,
            blacklist=self.blacklist,
            forensic=False,
        )  # type: RPMUtil
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
        self.dcrpm = DcRPM(self.rpmutil, self.args)  # type: DcRPM

    # run_recovery
    @patch("dcrpm.pidutil.send_signals")
    @patch("dcrpm.rpmutil.RPMUtil.recover_db")
    def test_run_recovery_dry_run(self, mock_recover, mock_kill):
        # type: (MagicMock, MagicMock) -> None
        self.args.dry_run = True
        self.dcrpm.run_recovery()
        mock_recover.assert_not_called()
        mock_kill.assert_not_called()

    # db_stat
    @patch("dcrpm.pidutil.send_signals")
    @patch("dcrpm.rpmutil.RPMUtil.db_stat")
    def test_db_stat_forensic(self, mock_db_stat, mock_kill):
        # type: (MagicMock, MagicMock) -> None
        self.args.forensic = True
        self.args.dry_run = True
        self.dcrpm.run()
        mock_db_stat.assert_called()
        mock_kill.assert_not_called()

    # run_rebuild
    @patch("dcrpm.rpmutil.RPMUtil.rebuild_db")
    def test_run_rebuild_dry_run(self, mock_rebuild):
        # type: (MagicMock) -> None
        self.args.dry_run = True
        self.dcrpm.run_rebuild()
        mock_rebuild.assert_not_called()

    # hardlink_db001
    @patch("os.unlink", side_effect=OSError())
    @patch("os.link")
    def test_hardlink_db001_link_exists(self, mock_symlink, mock_unlink):
        # type: (MagicMock, MagicMock) -> None
        p = self.dcrpm.hardlink_db001()
        old = join(self.dbpath, "__db.001")
        new = join(self.dbpath, "__dcrpm_py_inode_pointer")
        self.assertEqual(p, new)
        mock_unlink.assert_called_once()
        mock_symlink.assert_called_once_with(old, new)

    @patch("os.unlink")
    @patch("os.link", side_effect=OSError())
    def test_hardlink_db001_symlink_fails(self, mock_symlink, mock_unlink):
        # type: (MagicMock, MagicMock) -> None
        with self.assertRaises(DcRPMException):
            self.dcrpm.hardlink_db001()
        old = join(self.dbpath, "__db.001")
        new = join(self.dbpath, "__dcrpm_py_inode_pointer")
        mock_unlink.assert_called_once()
        mock_symlink.assert_called_once_with(old, new)

    # stale_yum_transactions_exist
    @patch(
        "os.listdir",
        return_value=[
            join(DcRPM.YUM_PATH, "file1"),
            join(DcRPM.YUM_PATH, "file2"),
            join(DcRPM.YUM_PATH, "file3"),
        ],
    )
    def test_stale_yum_transactions_no_exist(self, mock_iterdir):
        # type: (MagicMock) -> None
        self.assertFalse(self.dcrpm.stale_yum_transactions_exist())

    @patch(
        "os.listdir",
        return_value=[
            join(DcRPM.YUM_PATH, "file1"),
            join(DcRPM.YUM_PATH, "transaction-all.5"),
            join(DcRPM.YUM_PATH, "file3"),
        ],
    )
    def test_stale_yum_transactions_exist(self, mock_iterdir):
        # type: (MagicMock) -> None
        self.assertTrue(self.dcrpm.stale_yum_transactions_exist())

    # has_free_disk_space
    @patch("os.statvfs")
    def test_has_free_disk_space_success(self, mock_statvfs):
        # type: (MagicMock) -> None
        mock_statvfs.return_value = statvfs_result(
            4096, 108710048
        )  # type: statvfs_result
        self.assertTrue(self.dcrpm.has_free_disk_space())

    @patch("os.statvfs")
    def test_has_free_disk_space_fail(self, mock_statvfs):
        # type: (MagicMock) -> None
        mock_statvfs.return_value = statvfs_result(4096, 5)  # type: statvfs_result
        self.assertFalse(self.dcrpm.has_free_disk_space())
