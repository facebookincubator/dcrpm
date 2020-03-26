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

import os
import time
import typing as t  # noqa

import psutil
import testslide
from dcrpm import rpmutil, util
from dcrpm.util import CompletedProcess, DBNeedsRebuild, DBNeedsRecovery, DcRPMException
from tests.mock_process import make_mock_process


if t.TYPE_CHECKING:
    try:
        from unittest.mock import Mock
    except ImportError:
        from mock import Mock


def assert_called_like(mock, **kwargs):
    # type: (Mock, bool) -> None
    """
    Helper function to assert that `mock` was called with the calls listed in
    `call_mapping`, which looks like:
        {
            "method1": True,
            "method2": False,
        }
    which asserts mock.method1() was called, and mock.method2() was not.
    """
    if not kwargs:
        return
    for method, should_have_called in kwargs.items():
        attr = getattr(mock, method)
        if should_have_called:
            assert attr.call_count > 0
        else:
            assert attr.call_count == 0


class TestRPMUtil(testslide.TestCase):
    def setUp(self):
        # type: () -> None
        super(TestRPMUtil, self).setUp()
        self.rpm_path = "/usr/bin/rpm"  # type: str
        self.dbpath = "/var/lib/rpm"  # type: str
        self.recover_path = "/usr/bin/db_recover"  # type: str
        self.verify_path = "/usr/bin/db_verify"  # type: str
        self.stat_path = "/usr/bin/db_stat"  # type: str
        self.yum_complete_transaction_path = (
            "/usr/bin/yum-complete-transaction"
        )  # type: str
        self.blacklist = ["table1", "table2"]  # type: t.List[str]
        self.forensic = False  # type: bool
        self.rpmutil = rpmutil.RPMUtil(
            dbpath=self.dbpath,
            rpm_path=self.rpm_path,
            recover_path=self.recover_path,
            verify_path=self.verify_path,
            stat_path=self.stat_path,
            yum_complete_transaction_path=self.yum_complete_transaction_path,
            blacklist=self.blacklist,
            forensic=self.forensic,
        )  # type: rpmutil.RPMUtil
        self.rpmutil.tables = [
            "/var/lib/rpm/table0",
            "/var/lib/rpm/table1",
            "/var/lib/rpm/table2",
            "/var/lib/rpm/table3",
        ]

    # query
    def test_query_success(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .for_call(
                [self.rpm_path, "--dbpath", self.dbpath, "-q", "foo"],
                rpmutil.RPM_CHECK_TIMEOUT_SEC,
            )
            .to_return_value(
                CompletedProcess(stdout="\n".join(["foo-4.13.0-1.el7.centos.x86_64"]))
            )
            .and_assert_called_once()
        )
        self.rpmutil.query("foo")

    def test_query_failure(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .for_call(
                [self.rpm_path, "--dbpath", self.dbpath, "-q", "foo"],
                rpmutil.RPM_CHECK_TIMEOUT_SEC,
            )
            .to_return_value(
                CompletedProcess(stdout="\n".join(["perl-File-Path-2.09-2.el7.noarch"]))
            )
            .and_assert_called_once()
        )
        with self.assertRaises(DBNeedsRebuild):
            self.rpmutil.query("foo")

    # check_rpm_qa
    def test_check_rpm_qa_success(self):
        # type: () -> None
        self.mock_callable(rpmutil, "run_with_timeout").to_return_value(
            CompletedProcess(
                stdout="\n".join(
                    ["rpm{}".format(i) for i in range(rpmutil.MIN_ACCEPTABLE_PKG_COUNT)]
                )
            )
        ).and_assert_called_once()
        self.rpmutil.check_rpm_qa()

    def test_check_rpm_qa_not_enough_packages_linux(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .to_return_value(
                CompletedProcess(stdout="\n".join(["rpm%s" % i for i in range(5)]))
            )
            .and_assert_called_once()
        )
        (
            self.mock_callable(rpmutil, "read_os_name")
            .to_return_value("Linux")
            .and_assert_called_once()
        )
        with self.assertRaises(DBNeedsRecovery):
            self.rpmutil.check_rpm_qa()

    def test_check_rpm_qa_not_enough_packages_darwin(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .to_return_value(
                CompletedProcess(stdout="\n".join(["rpm%s" % i for i in range(5)]))
            )
            .and_assert_called_once()
        )
        (
            self.mock_callable(rpmutil, "read_os_name")
            .to_return_value("Darwin")
            .and_assert_called_once()
        )
        try:
            self.rpmutil.check_rpm_qa()
        except DBNeedsRecovery:
            self.fail("Package count check should be bypassed on macOS")

    def test_check_rpm_qa_raise_on_nonzero_rc(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .to_raise(DcRPMException)
            .and_assert_called_once()
        )
        with self.assertRaises(DBNeedsRecovery):
            self.rpmutil.check_rpm_qa()

    # recover_db
    def test_recover_db_success(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .to_return_value(CompletedProcess())
            .and_assert_called_once()
        )
        self.rpmutil.recover_db()

    # rebuild_db
    def test_rebuild_db_success(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .to_return_value(CompletedProcess())
            .and_assert_called_once()
        )
        self.rpmutil.rebuild_db()

    # check_tables
    def test_check_tables_success(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .to_return_value(CompletedProcess(returncode=0))
            .and_assert_called_once()
        )
        self.rpmutil.check_tables()

    def test_check_tables_raises_on_list_all(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .for_call(
                [self.rpm_path, "--dbpath", self.dbpath, "-qa", "--qf", "%{NAME}\\n"],
                timeout=rpmutil.RPM_CHECK_TIMEOUT_SEC,
                exception_to_raise=DBNeedsRebuild,
            )
            .to_raise(DBNeedsRebuild)
            .and_assert_called_once()
        )
        with self.assertRaises(DBNeedsRebuild):
            self.rpmutil.check_tables()

    def test_check_tables_success_on_no_rpms(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .for_call(
                [self.rpm_path, "--dbpath", self.dbpath, "-qa", "--qf", "%{NAME}\\n"],
                timeout=rpmutil.RPM_CHECK_TIMEOUT_SEC,
                exception_to_raise=DBNeedsRebuild,
            )
            .to_return_value(CompletedProcess(returncode=0, stdout=""))
            .and_assert_called_once()
        )
        self.rpmutil.check_tables()

    def test_check_tables_raises_on_query(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .for_call(
                [self.rpm_path, "--dbpath", self.dbpath, "-qa", "--qf", "%{NAME}\\n"],
                timeout=rpmutil.RPM_CHECK_TIMEOUT_SEC,
                exception_to_raise=DBNeedsRebuild,
            )
            .to_return_value(CompletedProcess(returncode=0, stdout="foo\nbaz\nfoo"))
            .and_assert_called_once()
        )
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .for_call(
                [self.rpm_path, "--dbpath", self.dbpath, "-q", "baz", "foo"],
                timeout=rpmutil.RPM_CHECK_TIMEOUT_SEC,
                exception_to_raise=DBNeedsRebuild,
            )
            .to_raise(DBNeedsRebuild)
            .and_assert_called_once()
        )
        with self.assertRaises(DBNeedsRebuild):
            self.rpmutil.check_tables()

    def test_check_tables_raises_on_uninstalled(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .for_call(
                [self.rpm_path, "--dbpath", self.dbpath, "-qa", "--qf", "%{NAME}\\n"],
                timeout=rpmutil.RPM_CHECK_TIMEOUT_SEC,
                exception_to_raise=DBNeedsRebuild,
            )
            .to_return_value(CompletedProcess(returncode=0, stdout="foo\nbaz\nfoo"))
            .and_assert_called_once()
        )
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .for_call(
                [self.rpm_path, "--dbpath", self.dbpath, "-q", "baz", "foo"],
                timeout=rpmutil.RPM_CHECK_TIMEOUT_SEC,
                exception_to_raise=DBNeedsRebuild,
            )
            .to_return_value(
                CompletedProcess(returncode=0, stdout="baz is not installed\nfoo")
            )
            .and_assert_called_once()
        )
        with self.assertRaises(DBNeedsRebuild):
            self.rpmutil.check_tables()

    def test_check_tables_(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .to_return_value(CompletedProcess(returncode=0, stdout=""))
            .and_assert_called_once()
        )
        self.rpmutil.check_tables()

    # verify_tables
    def test_verify_tables_success(self):
        # type: () -> None
        # Not blacklisted tables
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .for_call(
                [self.verify_path, "/var/lib/rpm/table0"],
                rpmutil.VERIFY_TIMEOUT_SEC,
                raise_on_nonzero=False,
            )
            .to_return_value(CompletedProcess())
            .and_assert_called_once()
        )
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .for_call(
                [self.verify_path, "/var/lib/rpm/table3"],
                rpmutil.VERIFY_TIMEOUT_SEC,
                raise_on_nonzero=False,
            )
            .to_return_value(CompletedProcess())
            .and_assert_called_once()
        )
        self.rpmutil.verify_tables()

    def test_verify_tables_all_blacklisted(self):
        # type: () -> None
        self.mock_callable(rpmutil, "run_with_timeout").and_assert_not_called()
        self.rpmutil.tables = self.rpmutil.tables[1:3]
        self.rpmutil.verify_tables()

    def test_verify_tables_fail(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .for_call(
                [self.verify_path, os.path.join(self.dbpath, "table0")],
                rpmutil.RPM_CHECK_TIMEOUT_SEC,
                raise_on_nonzero=False,
            )
            .to_return_value(CompletedProcess(returncode=1))
            .and_assert_called_once()
        )
        with self.assertRaises(DcRPMException):
            self.rpmutil.verify_tables()

    # clean_yum_transactions
    def test_clean_yum_transactions_success(self):
        # type: () -> None
        (
            self.mock_callable(rpmutil, "run_with_timeout")
            .to_return_value(CompletedProcess(returncode=0))
            .and_assert_called_once()
        )
        self.rpmutil.clean_yum_transactions()

    # kill_spinning_rpm_query_processes
    def test_kill_spinning_rpm_query_processes_success(self):
        # type: () -> None
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

        test_procs = [
            young_rpm,
            young_non_rpm,
            young_non_rpm2,
            old_bin_rpm,
            old_usr_bin_rpm,
            old_usr_bin_rpm_wait_throw,
            old_usr_bin_rpm_cmdline_throw,
            young_bin_rpm,
        ]  # type: t.List[psutil.Process]
        (
            self.mock_callable(psutil, "process_iter")
            .to_yield_values(test_procs)
            .and_assert_called_once()
        )
        self.mock_callable(time, "time").to_return_value(10000)

        self.rpmutil.kill_spinning_rpm_query_processes()

        assert_called_like(young_rpm, create_time=True, send_signal=False, wait=False)
        assert_called_like(
            young_non_rpm, create_time=False, send_signal=False, wait=False
        )
        assert_called_like(
            young_non_rpm2, create_time=False, send_signal=False, wait=False
        )
        assert_called_like(old_bin_rpm, create_time=True, send_signal=True, wait=True)
        assert_called_like(
            old_usr_bin_rpm, create_time=True, send_signal=True, wait=True
        )
        assert_called_like(
            old_usr_bin_rpm_wait_throw, create_time=True, send_signal=True, wait=True
        )
        assert_called_like(
            old_usr_bin_rpm_cmdline_throw,
            create_time=False,
            send_signal=False,
            wait=False,
        )
        assert_called_like(
            young_bin_rpm, create_time=True, send_signal=False, wait=False
        )
