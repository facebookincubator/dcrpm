#!/usr/bin/env python
#
# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the GPLv2 license found in the LICENSE
# file in the root directory of this source tree.
#

from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import json
import logging
import logging.config
import unittest

from dcrpm.dcrpm import DcRPM
from dcrpm.rpmutil import RPMUtil
from dcrpm.util import which
from tests.rpmdb import RPMDB


with open("tests/logging.json") as f:
    logging.config.dictConfig(json.load(f))

RPMDB.path = "tests/rpmdbs"


class DcrpmIntegrationTestBase(unittest.TestCase):
    def setUp(self):
        self.rpm_path = which("rpm")
        self.dbpath = "/tmp/"
        self.recover_path = which("db_recover")
        self.verify_path = which("db_verify")
        self.stat_path = which("db_stat")
        self.yum_complete_transaction_path = "/usr/sbin/yum-complete-transaction"
        self.blacklist = ["table1", "table2"]
        self.forensic = False

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
            logging_config_file="/var/log/blah.log",
            blacklist=["table2", "table3"],
            forensic=False,
        )

        self.rpmutil = RPMUtil(
            dbpath=self.dbpath,
            rpm_path=self.rpm_path,
            recover_path=self.recover_path,
            verify_path=self.verify_path,
            stat_path=self.stat_path,
            yum_complete_transaction_path=self.yum_complete_transaction_path,
            blacklist=self.blacklist,
            forensic=self.forensic,
        )

        # DcRPM
        self.dcrpm = DcRPM(self.rpmutil, self.args)
        logging.getLogger("status").handlers[0].trace = []

    # Helper for reading current logger trace
    def action_trace(self):
        return logging.getLogger("status").handlers[0].trace
