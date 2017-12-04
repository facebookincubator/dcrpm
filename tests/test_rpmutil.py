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

import subprocess
import unittest

from mock import Mock, call, patch

from .. import rpmutil
from ..util import (
    CompletedProcess,
    DcRPMException,
    DBNeedsRecovery,
)

run_str = __name__ + '.rpmutil.RPMUtil.run_with_timeout'


def make_mock_popen(
    stdout='',
    stderr='',
    returncode=0,
    communicate_raise=False,
):
    # type: (str, str, int, bool) -> Mock
    """
    Creates a simple mocked Popen object that responds to Popen.poll and
    Popen.communicate.
    """
    mock_popen = Mock()
    config = {
        'communicate.return_value': (stdout, stderr),
        'poll.return_value': returncode,
    }
    if communicate_raise:
        del config['communicate.return_value']
        config['communicate.side_effect'] = rpmutil.TimeoutExpired()
    mock_popen.configure_mock(**config)
    return mock_popen


class TestRPMUtil(unittest.TestCase):
    def setUp(self):
        self.rpmpath = rpmutil.RPM_PATH
        self.dbpath = '/var/lib/rpm'
        self.recover_path = '/opt/yum/bin/db48_recover'
        self.verify_path = '/opt/yum/bin/db48_verify'
        self.yum_complete_transaction_path = \
            '/opt/yum/bin/yum-complete-transaction'
        self.blacklist = [
            'table1',
            'table2',
        ]
        self.rpmutil = rpmutil.RPMUtil(
            dbpath=self.dbpath,
            recover_path=self.recover_path,
            verify_path=self.verify_path,
            yum_complete_transaction_path=self.yum_complete_transaction_path,
            blacklist=self.blacklist,
        )
        self.rpmutil.tables = [
            '/var/lib/rpm/table0',
            '/var/lib/rpm/table1',
            '/var/lib/rpm/table2',
            '/var/lib/rpm/table3',
        ]

    # check_rpm_qa
    @patch(
        run_str,
        return_value=CompletedProcess(
            stdout='\n'.join(
                [
                    'rpm{}'.format(i)
                    for i in range(rpmutil.MIN_ACCEPTABLE_PKG_COUNT)
                ]
            ),
        )
    )
    def test_check_rpm_qa_success(self, mock_run):
        self.rpmutil.check_rpm_qa()
        mock_run.assert_called_once_with(
            '{} --dbpath {} -qa'.format(self.rpmpath, self.dbpath),
            5,
        )

    @patch(
        run_str,
        return_value=CompletedProcess(
            stdout='\n'.join(['rpm{}'.format(i) for i in range(5)]),
        )
    )
    def test_check_rpm_qa_not_enough_packages(self, mock_run):
        with self.assertRaises(DBNeedsRecovery):
            self.rpmutil.check_rpm_qa()
        mock_run.assert_called_once_with(
            '{} --dbpath {} -qa'.format(self.rpmpath, self.dbpath),
            5,
        )

    @patch(run_str, return_value=CompletedProcess(returncode=1))
    def test_check_rpm_qa_raise_on_nonzero_rc(self, mock_run):
        with self.assertRaises(DBNeedsRecovery):
            self.rpmutil.check_rpm_qa()
        mock_run.assert_called_once_with(
            '{} --dbpath {} -qa'.format(self.rpmpath, self.dbpath),
            rpmutil.RPM_CHECK_TIMEOUT_SEC,
        )

    # recover_db
    @patch(run_str, return_value=CompletedProcess())
    def test_recover_db_success(self, mock_run):
        self.rpmutil.recover_db()
        mock_run.assert_called_once_with(
            '{} -h {}'.format(self.recover_path, self.dbpath),
            rpmutil.RECOVER_TIMEOUT_SEC,
        )

    # rebuild_db
    @patch(run_str, return_value=CompletedProcess())
    def test_rebuild_db_success(self, mock_run):
        self.rpmutil.rebuild_db()
        mock_run.assert_called_once_with(
            '{} --dbpath {} --rebuilddb'.format(rpmutil.RPM_PATH, self.dbpath),
            rpmutil.REBUILD_TIMEOUT_SEC,
        )

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
                    '{} {}/table0'.format(self.verify_path, self.dbpath),
                    rpmutil.VERIFY_TIMEOUT_SEC,
                    raise_on_nonzero=False,
                ),
                call(
                    '{} {}/table3'.format(self.verify_path, self.dbpath),
                    rpmutil.VERIFY_TIMEOUT_SEC,
                    raise_on_nonzero=False,
                ),
            ]
        )

    @patch(run_str)
    def test_verify_tables_all_blacklisted(self, mock_run):
        self.rpmutil.tables = self.rpmutil.tables[1:3]
        self.rpmutil.verify_tables()
        mock_run.assert_not_called()

    @patch(run_str, side_effect=2 * [CompletedProcess(returncode=1)])
    def test_verify_tables_fail(self, mock_run):
        with self.assertRaises(DcRPMException):
            self.rpmutil.verify_tables()
        mock_run.assert_called_once_with(
            '{} {}/table0'.format(self.verify_path, self.dbpath),
            rpmutil.VERIFY_TIMEOUT_SEC,
            raise_on_nonzero=False,
        )

    # clean_yum_transactions
    @patch(run_str, return_value=CompletedProcess(returncode=0))
    def test_clean_yum_transactions_success(self, mock_run):
        self.rpmutil.clean_yum_transactions()
        mock_run.assert_called_once_with(
            '{} --cleanup'.format(self.yum_complete_transaction_path),
            rpmutil.RPM_CHECK_TIMEOUT_SEC,
        )

    # run_with_timeout
    @patch('subprocess.Popen', return_value=make_mock_popen())
    def test_run_with_timeout_success(self, mock_popen):
        result = self.rpmutil.run_with_timeout('/bin/true', 5)
        self.assertEqual(result.returncode, 0)
        mock_popen.assert_called_once_with(
            '/bin/true',
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    @patch(
        'subprocess.Popen',
        return_value=make_mock_popen(returncode=1, communicate_raise=True),
    )
    def test_run_with_timeout_timeout(self, mock_popen):
        with self.assertRaises(DcRPMException):
            self.rpmutil.run_with_timeout('/bin/true', 5)
        mock_popen.assert_called_once_with(
            '/bin/true',
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    @patch('subprocess.Popen', return_value=make_mock_popen(returncode=1))
    def test_run_with_timeout_raise_on_nonzero(self, mock_popen):
        with self.assertRaises(DcRPMException):
            self.rpmutil.run_with_timeout('/bin/true', 5)
        mock_popen.assert_called_once_with(
            '/bin/true',
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    # Note that this runs a real `sleep 2` command. This ensures the timeout
    # mechanism works correctly with signals/alarms.
    def test_run_with_timeout_times_out_real_command(self):
        with self.assertRaises(DcRPMException):
            self.rpmutil.run_with_timeout('/bin/sleep 2', 1)

    @patch('subprocess.Popen', return_value=make_mock_popen(returncode=1))
    def test_run_with_timeout_no_raise_on_nonzero(self, mock_popen):
        result = self.rpmutil.run_with_timeout(
            '/bin/true',
            5,
            raise_on_nonzero=False,
        )
        self.assertEqual(result.returncode, 1)
        mock_popen.assert_called_once_with(
            '/bin/true',
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
