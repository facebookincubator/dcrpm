#!/usr/bin/env python
#
# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the GPLv2 license found in the LICENSE
# file in the root directory of this source tree.
#

from __future__ import absolute_import, division, print_function, unicode_literals

import time
import unittest

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch

from dcrpm.yum import Yum
from tests.mock_process import make_mock_process


pidutil_mod = "dcrpm.pidutil"


class TestYum(unittest.TestCase):
    def setUp(self):
        self.yum = Yum()

    # check_stuck
    @patch(pidutil_mod + ".pidfile_info", side_effect=IOError())
    def test_check_stuck_filenotfound(self, mock_pidinfo):
        self.assertTrue(self.yum.check_stuck())

    @patch(pidutil_mod + ".pidfile_info", side_effect=ValueError())
    def test_check_stuck_valueerror(self, mock_pidinfo):
        self.assertFalse(self.yum.check_stuck())

    @patch(pidutil_mod + ".pidfile_info", side_effect=Exception())
    def test_check_stuck_other_exception(self, mock_pidinfo):
        self.assertFalse(self.yum.check_stuck())

    @patch(pidutil_mod + ".pidfile_info", return_value=(12345, int(time.time()) - 3600))
    def test_check_stuck_yumpid_not_old_enough(self, mock_pidinfo):
        self.assertTrue(self.yum.check_stuck())

    @patch(
        pidutil_mod + ".pidfile_info", return_value=(12345, int(time.time()) - 7 * 3600)
    )
    @patch(pidutil_mod + ".process", return_value=None)
    def test_check_stuck_yumpid_no_such_process(self, mock_proc, mock_pidinfo):
        self.assertFalse(self.yum.check_stuck())

    @patch(
        pidutil_mod + ".pidfile_info", return_value=(12345, int(time.time()) - 7 * 3600)
    )
    @patch(
        pidutil_mod + ".process",
        return_value=make_mock_process(pid=12345, open_files=[], name="yum"),
    )
    def test_check_stuck_kill_yumpid(self, mock_proc, mock_pidinfo):
        self.assertTrue(self.yum.check_stuck())

    @patch(
        pidutil_mod + ".pidfile_info", return_value=(12345, int(time.time()) - 7 * 3600)
    )
    @patch(pidutil_mod + ".process", return_value=None)
    def test_check_stuck_kill_yumpid_no_such_process(self, mock_proc, mock_pidinfo):
        self.assertFalse(self.yum.check_stuck())

    @patch(
        pidutil_mod + ".pidfile_info", return_value=(12345, int(time.time()) - 7 * 3600)
    )
    @patch(pidutil_mod + ".process", return_value=None)
    def test_check_stuck_kill_yumpid_timeout(self, mock_proc, mock_pidinfo):
        self.assertFalse(self.yum.check_stuck())
