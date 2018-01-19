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

import unittest

from mock import call, patch

from dcrpm import rpmutil
from dcrpm.util import (
    CompletedProcess,
    DcRPMException,
    DBNeedsRecovery,
)

run_str = __name__ + '.rpmutil.run_with_timeout'


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
        self.assertIn(
            '{} --dbpath {} -qa'.format(self.rpmpath, self.dbpath),
            mock_run.call_args[0]
        )
        self.assertIn(rpmutil.RPM_CHECK_TIMEOUT_SEC, mock_run.call_args[0])
        mock_run.assert_called_once()

    @patch(
        run_str,
        return_value=CompletedProcess(
            stdout='\n'.join(['rpm{}'.format(i) for i in range(5)]),
        )
    )
    def test_check_rpm_qa_not_enough_packages(self, mock_run):
        with self.assertRaises(DBNeedsRecovery):
            self.rpmutil.check_rpm_qa()
        self.assertIn(
            '{} --dbpath {} -qa'.format(self.rpmpath, self.dbpath),
            mock_run.call_args[0]
        )
        self.assertIn(rpmutil.RPM_CHECK_TIMEOUT_SEC, mock_run.call_args[0])
        mock_run.assert_called_once()

    @patch(run_str, return_value=CompletedProcess(returncode=1))
    def test_check_rpm_qa_raise_on_nonzero_rc(self, mock_run):
        with self.assertRaises(DBNeedsRecovery):
            self.rpmutil.check_rpm_qa()
        self.assertIn(
            '{} --dbpath {} -qa'.format(self.rpmpath, self.dbpath),
            mock_run.call_args[0]
        )
        self.assertIn(rpmutil.RPM_CHECK_TIMEOUT_SEC, mock_run.call_args[0])
        mock_run.assert_called_once()

    # recover_db
    @patch(run_str, return_value=CompletedProcess())
    def test_recover_db_success(self, mock_run):
        self.rpmutil.recover_db()
        self.assertIn(
            '{} -h {}'.format(self.recover_path, self.dbpath),
            mock_run.call_args[0]
        )
        self.assertIn(rpmutil.RECOVER_TIMEOUT_SEC, mock_run.call_args[0])
        mock_run.assert_called_once()

    # rebuild_db
    @patch(run_str, return_value=CompletedProcess())
    def test_rebuild_db_success(self, mock_run):
        self.rpmutil.rebuild_db()
        self.assertIn(
            '{} --dbpath {} --rebuilddb'.format(rpmutil.RPM_PATH, self.dbpath),
            mock_run.call_args[0]
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
        self.assertIn(
            '{} --cleanup'.format(self.yum_complete_transaction_path),
            mock_run.call_args[0]
        )
        self.assertIn(rpmutil.RPM_CHECK_TIMEOUT_SEC, mock_run.call_args[0])
        mock_run.assert_called_once()
