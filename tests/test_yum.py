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

import time

import testslide
from dcrpm import pidutil, yum
from tests.mock_process import make_mock_process


class TestYum(testslide.TestCase):
    def setUp(self):
        # type: () -> None
        super(TestYum, self).setUp()
        self.yum = yum.Yum()  # type: yum.Yum

    # check_stuck
    def test_check_stuck_filenotfound(self):
        # type: () -> None
        (
            self.mock_callable(pidutil, "pidfile_info")
            .for_call(yum.YUM_PID_PATH)
            .to_raise(IOError())
            .and_assert_called_once()
        )
        self.assertTrue(self.yum.check_stuck())

    def test_check_stuck_valueerror(self):
        # type: () -> None
        (
            self.mock_callable(pidutil, "pidfile_info")
            .for_call(yum.YUM_PID_PATH)
            .to_raise(ValueError())
            .and_assert_called_once()
        )
        self.assertFalse(self.yum.check_stuck())

    def test_check_stuck_other_exception(self):
        # type: () -> None
        (
            self.mock_callable(pidutil, "pidfile_info")
            .for_call(yum.YUM_PID_PATH)
            .to_raise(Exception())
            .and_assert_called_once()
        )
        self.assertFalse(self.yum.check_stuck())

    def test_check_stuck_yumpid_not_old_enough(self):
        # type: () -> None
        (
            self.mock_callable(pidutil, "pidfile_info")
            .for_call(yum.YUM_PID_PATH)
            .to_return_value((1234, int(time.time()) - 3600))
            .and_assert_called_once()
        )
        self.assertTrue(self.yum.check_stuck())

    def test_check_stuck_yumpid_no_such_process(self):
        # type: () -> None
        (
            self.mock_callable(pidutil, "pidfile_info")
            .for_call(yum.YUM_PID_PATH)
            .to_return_value((12345, int(time.time()) - 7 * 3600))
            .and_assert_called_once()
        )
        (
            self.mock_callable(pidutil, "process")
            .for_call(12345)
            .to_return_value(None)
            .and_assert_called_once()
        )
        self.assertFalse(self.yum.check_stuck())

    def test_check_stuck_kill_yumpid(self):
        # type: () -> None
        (
            self.mock_callable(pidutil, "pidfile_info")
            .for_call(yum.YUM_PID_PATH)
            .to_return_value((12345, int(time.time()) - 7 * 3600))
            .and_assert_called_once()
        )
        (
            self.mock_callable(pidutil, "process")
            .for_call(12345)
            .to_return_value(make_mock_process(pid=12345, open_files=[], name="yum"))
            .and_assert_called_once()
        )
        self.assertTrue(self.yum.check_stuck())

    def test_check_stuck_kill_yumpid_no_such_process(self):
        # type: () -> None
        (
            self.mock_callable(pidutil, "pidfile_info")
            .for_call(yum.YUM_PID_PATH)
            .to_return_value((12345, int(time.time()) - 7 * 3600))
            .and_assert_called_once()
        )
        (
            self.mock_callable(pidutil, "process")
            .for_call(12345)
            .to_return_value(None)
            .and_assert_called_once()
        )
        self.assertFalse(self.yum.check_stuck())

    def test_check_stuck_kill_yumpid_timeout(self):
        # type: () -> None
        (
            self.mock_callable(pidutil, "pidfile_info")
            .for_call(yum.YUM_PID_PATH)
            .to_return_value((12345, int(time.time()) - 7 * 3600))
            .and_assert_called_once()
        )
        (
            self.mock_callable(pidutil, "process")
            .for_call(12345)
            .to_return_value(None)
            .and_assert_called_once()
        )
        self.assertFalse(self.yum.check_stuck())
