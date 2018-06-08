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

import argparse
import os
import unittest
import logging
import logging.config
import json

from ..dcrpm import DcRPM
from ..rpmutil import RPMUtil, RPM_PATH
from .rpmdb import RPMDB

with open(os.path.join(os.path.dirname(__file__), 'logging.json')) as f:
    logging.config.dictConfig(json.load(f))

RPMDB.path = os.path.join(os.path.dirname(__file__), 'rpmdbs')


class DcrpmIntegrationTestBase(unittest.TestCase):

    def setUp(self):
        self.rpmpath = RPM_PATH
        self.dbpath = '/tmp/'
        self.recover_path = '/bin/db_recover'
        self.verify_path = '/bin/db_verify'
        self.yum_complete_transaction_path = \
            '/opt/yum/bin/yum-complete-transaction'
        self.blacklist = [
            'table1',
            'table2',
        ]
        self.forensic = False

        # Args
        self.args = argparse.Namespace(
            dry_run=False,
            check_stuck_yum=True,
            recover_path=self.recover_path,
            verify_path=self.verify_path,
            clean_yum_transactions=False,
            yum_complete_transaction_path=self.yum_complete_transaction_path,
            dbpath=self.dbpath,
            run_yum_clean=False,
            max_passes=5,
            minspace=150 * 1048576,
            verbose=False,
            logging_config_file='/var/log/blah.log',
            blacklist=['table2', 'table3'],
            forensic=False,
        )

        self.rpmutil = RPMUtil(
            dbpath=self.dbpath,
            recover_path=self.recover_path,
            verify_path=self.verify_path,
            yum_complete_transaction_path=self.yum_complete_transaction_path,
            blacklist=self.blacklist,
            forensic=self.forensic,
        )

        # DcRPM
        self.dcrpm = DcRPM(self.rpmutil, self.args)

    def action_trace(self):
        # Helper for reading current logger trace
        return logging.getLogger('status').handlers[0].trace
