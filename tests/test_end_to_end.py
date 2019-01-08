#!/usr/bin/env python
#
# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the GPLv2 license found in the LICENSE
# file in the root directory of this source tree.
#

from __future__ import absolute_import, division, print_function, unicode_literals

from tests.dcrpm_integration_test_base import DcrpmIntegrationTestBase
from tests.rpmdb import RPMDB


class DcrpmIntegrationTest(DcrpmIntegrationTestBase):

    # Fedora release 26 (Twenty Six)
    # dnf-yum-2.7.5-2.fc26.noarch
    # rpm-4.13.1-1.fc26.x86_64
    # rpm-libs-4.13.1-1.fc26.x86_64
    @RPMDB.from_file("rpmdb_fedora26")
    def test_rpmdb_fedora26(self, dbpath):
        self.rpmutil.dbpath = dbpath
        self.rpmutil.populate_tables()
        self.rpmutil._read_os_release = lambda: {"ID": "fedora"}
        self.dcrpm.args.dbpath = dbpath
        run_result = self.dcrpm.run()
        self.assertEqual(self.action_trace(), [])
        self.assertTrue(run_result)

    # TODO: figure out a way to gracefully skip this on c7, T30275604
    # CentOS release 6.9 (Final)
    # yum-3.2.29-81.el6.centos.noarch
    # rpm-4.8.0-55.el6.x86_64
    # rpm-libs-4.8.0-55.el6.x86_64
    # @RPMDB.from_file('rpmdb_centos6')
    # def test_rpmdb_centos6(self, dbpath):
    #     self.rpmutil.dbpath = dbpath
    #     self.rpmutil.populate_tables()
    #     self.rpmutil._read_os_release = lambda: {'ID': 'centos'}
    #     self.dcrpm.args.dbpath = dbpath
    #     self.dcrpm.run()
    #     self.assertEqual(
    #         self.action_trace(),
    #         ['db_recovery'],
    #     )

    # CentOS Linux release 7.4.1708 (Core)
    # yum-3.4.3-154.el7.centos.1.noarch
    # rpm-4.11.3-25.el7.x86_64
    # rpm-libs-4.11.3-25.el7.x86_64
    @RPMDB.from_file("rpmdb_centos7")
    def test_rpmdb_centos7(self, dbpath):
        self.rpmutil.dbpath = dbpath
        self.rpmutil.populate_tables()
        self.rpmutil._read_os_release = lambda: {"ID": "centos"}
        self.dcrpm.args.dbpath = dbpath
        run_result = self.dcrpm.run()
        self.assertEqual(self.action_trace(), [])
        self.assertTrue(run_result)

    # CentOS Linux release 7.4.1708 (Core)
    # yum-3.4.3-154.el7.centos.1.noarch
    # rpm-4.11.3-25.el7.x86_64
    # rpm-libs-4.11.3-25.el7.x86_64
    @RPMDB.from_file("rpmdb_centos7_missing_index")
    def test_rpmdb_centos7_missing_index(self, dbpath):
        self.rpmutil.dbpath = dbpath
        self.rpmutil.populate_tables()
        self.rpmutil._read_os_release = lambda: {"ID": "centos"}
        self.dcrpm.args.dbpath = dbpath
        run_result = self.dcrpm.run()
        self.assertEqual(self.action_trace(), [])
        self.assertTrue(run_result)
