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

import time
import unittest

from mock import patch

from tests.mock_process import make_mock_process
from dcrpm.stuckyum import StuckYum

pidutil_mod = 'dcrpm.pidutil'


class TestStuckYum(unittest.TestCase):
    def setUp(self):
        self.stuckyum = StuckYum()

    # run
    @patch(pidutil_mod + '.pidfile_info', side_effect=IOError())
    def test_run_filenotfound(self, mock_pidinfo):
        self.assertTrue(self.stuckyum.run())

    @patch(pidutil_mod + '.pidfile_info', side_effect=ValueError())
    def test_run_valueerror(self, mock_pidinfo):
        self.assertFalse(self.stuckyum.run())

    @patch(pidutil_mod + '.pidfile_info', side_effect=Exception())
    def test_run_other_exception(self, mock_pidinfo):
        self.assertFalse(self.stuckyum.run())

    @patch(
        pidutil_mod + '.pidfile_info',
        return_value=(12345, int(time.time()) - 3600)
    )
    def test_run_yumpid_not_old_enough(self, mock_pidinfo):
        self.assertTrue(self.stuckyum.run())

    @patch(
        pidutil_mod + '.pidfile_info',
        return_value=(12345, int(time.time()) - 7 * 3600)
    )
    @patch(pidutil_mod + '.process', return_value=None)
    def test_run_yumpid_no_such_process(self, mock_proc, mock_pidinfo):
        self.assertFalse(self.stuckyum.run())

    @patch(
        pidutil_mod + '.pidfile_info',
        return_value=(12345, int(time.time()) - 7 * 3600)
    )
    @patch(
        pidutil_mod + '.process',
        return_value=make_mock_process(pid=12345, open_files=[], name='yum')
    )
    def test_run_kill_yumpid(self, mock_proc, mock_pidinfo):
        self.assertTrue(self.stuckyum.run())

    @patch(
        pidutil_mod + '.pidfile_info',
        return_value=(12345, int(time.time()) - 7 * 3600)
    )
    @patch(pidutil_mod + '.process', return_value=None)
    def test_run_kill_yumpid_no_such_process(self, mock_proc, mock_pidinfo):
        self.assertFalse(self.stuckyum.run())

    @patch(
        pidutil_mod + '.pidfile_info',
        return_value=(12345, int(time.time()) - 7 * 3600)
    )
    @patch(pidutil_mod + '.process', return_value=None)
    def test_run_kill_yumpid_timeout(self, mock_proc, mock_pidinfo):
        self.assertFalse(self.stuckyum.run())
