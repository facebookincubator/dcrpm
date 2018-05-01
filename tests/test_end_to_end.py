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

from .dcrpm_integration_test_base import DcrpmIntegrationTestBase
from .rpmdb import RPMDB


class DcrpmIntegrationTest(DcrpmIntegrationTestBase):

    # Fedora release 26 (Twenty Six)
    # dnf-yum-2.7.5-2.fc26.noarch
    # rpm-4.13.1-1.fc26.x86_64
    # rpm-libs-4.13.1-1.fc26.x86_64
    @RPMDB.from_file('rpmdb_fedora26')
    def test_rpmdb_fedora26(self, dbpath):
        self.rpmutil.dbpath = dbpath
        self.dcrpm.args.dbpath = dbpath
        self.dcrpm.run()
        self.assertEquals(
            self.action_trace(),
            [],
        )

    # CentOS release 6.9 (Final)
    # yum-3.2.29-81.el6.centos.noarch
    # rpm-4.8.0-55.el6.x86_64
    # rpm-libs-4.8.0-55.el6.x86_64
    @RPMDB.from_file('rpmdb_centos6')
    def test_rpmdb_centos6(self, dbpath):
        self.rpmutil.dbpath = dbpath
        self.dcrpm.args.dbpath = dbpath
        self.dcrpm.run()
        self.assertEquals(
            self.action_trace(),
            ['db_recovery'],
        )

    # CentOS Linux release 7.4.1708 (Core)
    # yum-3.4.3-154.el7.centos.1.noarch
    # rpm-4.11.3-25.el7.x86_64
    # rpm-libs-4.11.3-25.el7.x86_64
    @RPMDB.from_file('rpmdb_centos7')
    def test_rpmdb_centos7(self, dbpath):
        self.rpmutil.dbpath = dbpath
        self.dcrpm.args.dbpath = dbpath
        self.dcrpm.run()
        self.assertEquals(
            self.action_trace(),
            [],
        )
