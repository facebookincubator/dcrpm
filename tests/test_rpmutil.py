#!/usr/bin/env python
#
# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the GPLv2 license found in the LICENSE
# file in the root directory of this source tree.
#

from __future__ import absolute_import, division, print_function, unicode_literals

import unittest
from typing import Dict

try:
    from unittest.mock import Mock, call, patch
except ImportError:
    from mock import Mock, call, patch

from dcrpm import rpmutil
from dcrpm.util import CompletedProcess, DBNeedsRebuild, DBNeedsRecovery, DcRPMException
from tests.mock_process import make_mock_process


BASE = __name__ + ".rpmutil"
run_str = BASE + ".run_with_timeout"


def assert_called_like(mock, call_mapping):
    # type: (Mock, Dict[str, bool]) -> None
    """
    Helper function to assert that `mock` was called with the calls listed in
    `call_mapping`, which looks like:
        {
            "method1": True,
            "method2": False,
        }
    which asserts mock.method1() was called, and mock.method2() was not.
    """
    if not call_mapping:
        return
    for method, should_have_called in call_mapping.items():
        attr = getattr(mock, method)
        if should_have_called:
            assert attr.call_count > 0
        else:
            assert attr.call_count == 0


class TestRPMUtil(unittest.TestCase):
    def setUp(self):
        self.rpm_path = "/usr/bin/rpm"
        self.dbpath = "/var/lib/rpm"
        self.recover_path = "/usr/bin/db_recover"
        self.verify_path = "/usr/bin/db_verify"
        self.stat_path = "/usr/bin/db_stat"
        self.yum_complete_transaction_path = "/usr/bin/yum-complete-transaction"
        self.blacklist = ["table1", "table2"]
        self.forensic = (False,)
        self.rpmutil = rpmutil.RPMUtil(
            dbpath=self.dbpath,
            rpm_path=self.rpm_path,
            recover_path=self.recover_path,
            verify_path=self.verify_path,
            stat_path=self.stat_path,
            yum_complete_transaction_path=self.yum_complete_transaction_path,
            blacklist=self.blacklist,
            forensic=self.forensic,
        )
        self.rpmutil.tables = [
            "/var/lib/rpm/table0",
            "/var/lib/rpm/table1",
            "/var/lib/rpm/table2",
            "/var/lib/rpm/table3",
        ]

    # query
    @patch(
        run_str,
        return_value=CompletedProcess(
            stdout="\n".join(["foo-4.13.0-1.el7.centos.x86_64"])
        ),
    )
    def test_query_success(self, mock_run):
        test_rpm_name = "foo"
        self.rpmutil.query("foo")
        self.assertIn(
            "{} --dbpath {} -q {}".format(self.rpm_path, self.dbpath, test_rpm_name),
            mock_run.call_args[0],
        )
        self.assertIn(rpmutil.RPM_CHECK_TIMEOUT_SEC, mock_run.call_args[0])
        mock_run.assert_called_once()

    @patch(
        run_str,
        return_value=CompletedProcess(
            stdout="\n".join(["perl-File-Path-2.09-2.el7.noarch"])
        ),
    )
    def test_query_failure(self, mock_run):
        with self.assertRaises(DBNeedsRebuild):
            self.rpmutil.query("foo")

    # check_rpm_qa
    @patch(
        run_str,
        return_value=CompletedProcess(
            stdout="\n".join(
                ["rpm{}".format(i) for i in range(rpmutil.MIN_ACCEPTABLE_PKG_COUNT)]
            )
        ),
    )
    def test_check_rpm_qa_success(self, mock_run):
        self.rpmutil.check_rpm_qa()
        self.assertIn(
            "{} --dbpath {} -qa".format(self.rpm_path, self.dbpath),
            mock_run.call_args[0],
        )
        self.assertIn(rpmutil.RPM_CHECK_TIMEOUT_SEC, mock_run.call_args[0])
        mock_run.assert_called_once()

    @patch(
        run_str,
        return_value=CompletedProcess(
            stdout="\n".join(["rpm{}".format(i) for i in range(5)])
        ),
    )
    def test_check_rpm_qa_not_enough_packages(self, mock_run):
        with self.assertRaises(DBNeedsRecovery):
            self.rpmutil.check_rpm_qa()
        self.assertIn(
            "{} --dbpath {} -qa".format(self.rpm_path, self.dbpath),
            mock_run.call_args[0],
        )
        self.assertIn(rpmutil.RPM_CHECK_TIMEOUT_SEC, mock_run.call_args[0])
        mock_run.assert_called_once()

    @patch(run_str, return_value=CompletedProcess(returncode=1))
    def test_check_rpm_qa_raise_on_nonzero_rc(self, mock_run):
        with self.assertRaises(DBNeedsRecovery):
            self.rpmutil.check_rpm_qa()
        self.assertIn(
            "{} --dbpath {} -qa".format(self.rpm_path, self.dbpath),
            mock_run.call_args[0],
        )
        self.assertIn(rpmutil.RPM_CHECK_TIMEOUT_SEC, mock_run.call_args[0])
        mock_run.assert_called_once()

    # recover_db
    @patch(run_str, return_value=CompletedProcess())
    def test_recover_db_success(self, mock_run):
        self.rpmutil.recover_db()
        self.assertIn(
            "{} -h {}".format(self.recover_path, self.dbpath), mock_run.call_args[0]
        )
        self.assertIn(rpmutil.RECOVER_TIMEOUT_SEC, mock_run.call_args[0])
        mock_run.assert_called_once()

    # rebuild_db
    @patch(run_str, return_value=CompletedProcess())
    def test_rebuild_db_success(self, mock_run):
        self.rpmutil.rebuild_db()
        self.assertIn(
            "{} --dbpath {} --rebuilddb".format(self.rpm_path, self.dbpath),
            mock_run.call_args[0],
        )
        self.assertIn(rpmutil.REBUILD_TIMEOUT_SEC, mock_run.call_args[0])
        mock_run.assert_called_once()

    # check_tables
    @patch(run_str, return_value=CompletedProcess(returncode=1))
    def test_check_tables_success(self, mock_run):
        self.rpmutil.check_tables()

    # verify_tables
    @patch(run_str, side_effect=2 * [CompletedProcess()])
    def test_verify_tables_success(self, mock_run):
        self.rpmutil.verify_tables()
        self.assertEqual(mock_run.call_count, 2)
        mock_run.assert_has_calls(
            [
                call(
                    "{} {}/table0".format(self.verify_path, self.dbpath),
                    rpmutil.VERIFY_TIMEOUT_SEC,
                    raise_on_nonzero=False,
                ),
                call(
                    "{} {}/table3".format(self.verify_path, self.dbpath),
                    rpmutil.VERIFY_TIMEOUT_SEC,
                    raise_on_nonzero=False,
                ),
            ]
        )

    @patch(run_str)
    def test_verify_tables_all_blacklisted(self, mock_run):
        self.rpmutil.tables = self.rpmutil.tables[1:3]
        self.rpmutil.verify_tables()
        self.assertEqual(mock_run.call_count, 0)

    @patch(run_str, side_effect=2 * [CompletedProcess(returncode=1)])
    def test_verify_tables_fail(self, mock_run):
        with self.assertRaises(DcRPMException):
            self.rpmutil.verify_tables()
        mock_run.assert_called_once_with(
            "{} {}/table0".format(self.verify_path, self.dbpath),
            rpmutil.VERIFY_TIMEOUT_SEC,
            raise_on_nonzero=False,
        )

    # clean_yum_transactions
    @patch(run_str, return_value=CompletedProcess(returncode=0))
    def test_clean_yum_transactions_success(self, mock_run):
        self.rpmutil.clean_yum_transactions()
        self.assertIn(
            "{} --cleanup".format(self.yum_complete_transaction_path),
            mock_run.call_args[0],
        )
        self.assertIn(rpmutil.YUM_COMPLETE_TIMEOUT_SEC, mock_run.call_args[0])
        mock_run.assert_called_once()

    # kill_spinning_rpm_query_processes
    @patch("psutil.process_iter")
    @patch("time.time")
    def test_kill_spinning_rpm_query_processes_success(self, mock_time, mock_iter):
        mock_time.return_value = 10000
        young_rpm = make_mock_process(
            123, cmdline="rpm -q foo-124.x86_64", create_time=9000
        )
        young_non_rpm = make_mock_process(456, cmdline="java foobar", create_time=8000)
        young_non_rpm2 = make_mock_process(789, cmdline="ps aux", create_time=8000)
        old_bin_rpm = make_mock_process(
            111, cmdline="/bin/rpm -q bar-456.x86_64", create_time=3000
        )
        old_usr_bin_rpm = make_mock_process(
            222, cmdline="/usr/bin/rpm -something -q bar-456.x86_64", create_time=2000
        )
        old_usr_bin_rpm_wait_throw = make_mock_process(
            222,
            cmdline="/usr/bin/rpm -q bar-456.x86_64",
            create_time=1000,
            wait_throw=True,
        )
        old_usr_bin_rpm_cmdline_throw = make_mock_process(
            222,
            cmdline="/usr/bin/rpm -q bar-456.x86_64",
            create_time=4000,
            cmdline_throw=True,
        )
        young_bin_rpm = make_mock_process(
            333, cmdline="/bin/rpm -q bar-788.x86_64", create_time=9000
        )
        mock_iter.return_value = [
            young_rpm,
            young_non_rpm,
            young_non_rpm2,
            old_bin_rpm,
            old_usr_bin_rpm,
            old_usr_bin_rpm_wait_throw,
            old_usr_bin_rpm_cmdline_throw,
            young_bin_rpm,
        ]

        self.rpmutil.kill_spinning_rpm_query_processes()

        assert_called_like(
            young_rpm, {"create_time": True, "send_signal": False, "wait": False}
        )
        assert_called_like(
            young_non_rpm, {"create_time": False, "send_signal": False, "wait": False}
        )
        assert_called_like(
            young_non_rpm2, {"create_time": False, "send_signal": False, "wait": False}
        )
        assert_called_like(
            old_bin_rpm, {"create_time": True, "send_signal": True, "wait": True}
        )
        assert_called_like(
            old_usr_bin_rpm, {"create_time": True, "send_signal": True, "wait": True}
        )
        assert_called_like(
            old_usr_bin_rpm_wait_throw,
            {"create_time": True, "send_signal": True, "wait": True},
        )
        assert_called_like(
            old_usr_bin_rpm_cmdline_throw,
            {"create_time": False, "send_signal": False, "wait": False},
        )
        assert_called_like(
            young_bin_rpm, {"create_time": True, "send_signal": False, "wait": False}
        )
