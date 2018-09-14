#!/usr/bin/env python
#
# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the GPLv2 license found in the LICENSE
# file in the root directory of this source tree.
#

from __future__ import absolute_import, division, print_function, unicode_literals

import math
import signal
import subprocess
import time
import unittest

try:
    from unittest.mock import Mock, call, patch
except ImportError:
    from mock import Mock, call, patch

from dcrpm.util import (
    DcRPMException,
    TimeoutExpired,
    alarm_handler,
    call_with_timeout,
    kindly_end,
    run_with_timeout,
)


def make_mock_popen(
    stdout="", stderr="", returncode=0, communicate_raise=False, terminate_raise=False
):
    # type: (str, str, int, bool, bool) -> Mock
    """
    Creates a simple mocked Popen object that responds to Popen.poll and
    Popen.communicate.
    """
    mock_popen_obj = Mock()
    config = {"poll.return_value": returncode}
    if communicate_raise:
        config["communicate.side_effect"] = TimeoutExpired()
    else:
        config["communicate.return_value"] = (stdout, stderr)
    if terminate_raise:
        config["terminate.side_effect"] = TimeoutExpired()
    mock_popen_obj.configure_mock(**config)
    return mock_popen_obj


class TestUtil(unittest.TestCase):
    # call_with_timeout
    @patch("signal.signal")
    @patch("signal.alarm")
    def test_call_with_timeout_success(self, mock_alarm, mock_signal):
        result = call_with_timeout(math.floor, 2, args=[2.5])
        self.assertEqual(result, 2.0)
        mock_alarm.assert_has_calls([call(2), call(0)])
        mock_signal.assert_called_once_with(signal.SIGALRM, alarm_handler)

    def test_call_with_timeout_real_raises(self):
        with self.assertRaises(TimeoutExpired):
            call_with_timeout(time.sleep, 1, args=[2])

    def test_call_with_timeout_real_no_raises_returns_none(self):
        result = call_with_timeout(time.sleep, 1, raise_=False, args=[2])
        self.assertIsNone(result)

    # run_with_timeout
    @patch("subprocess.Popen", return_value=make_mock_popen())
    def test_run_with_timeout_success(self, mock_popen):
        result = run_with_timeout("/bin/true", 5)
        self.assertEqual(result.returncode, 0)
        mock_popen.assert_called_once_with(
            "/bin/true",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )

    @patch("subprocess.Popen")
    def test_run_with_timeout_timeout(self, mock_popen):
        mock_popen.return_value = make_mock_popen(communicate_raise=True)
        with self.assertRaises(DcRPMException):
            run_with_timeout("/bin/true", 5)
        mock_popen.return_value.kill.assert_not_called()

    @patch("subprocess.Popen")
    def test_run_with_timeout_terminates_on_timeout(self, mock_popen):
        mock_popen.return_value = make_mock_popen(communicate_raise=True)
        with self.assertRaises(DcRPMException):
            run_with_timeout("/bin/true", 5)
        mock_popen.return_value.terminate.assert_called()
        mock_popen.return_value.kill.assert_not_called()

    @patch("subprocess.Popen")
    def test_run_with_timeout_kills_on_terminate_timeout(self, mock_popen):
        mock_popen.return_value = make_mock_popen(
            communicate_raise=True, terminate_raise=True
        )
        with self.assertRaises(DcRPMException):
            run_with_timeout("/bin/true", 5)
        mock_popen.return_value.terminate.assert_called()
        mock_popen.return_value.kill.assert_called()

    @patch("subprocess.Popen", return_value=make_mock_popen(returncode=1))
    def test_run_with_timeout_raise_on_nonzero(self, mock_popen):
        with self.assertRaises(DcRPMException):
            run_with_timeout("/bin/true", 5)

    @patch("subprocess.Popen", return_value=make_mock_popen(returncode=1))
    def test_run_with_timeout_no_raise_on_nonzero(self, mock_popen):
        result = run_with_timeout("/bin/true", 5, raise_on_nonzero=False)
        self.assertEqual(result.returncode, 1)

    @patch("subprocess.Popen")
    def test_run_with_timeout_no_raise_on_timeout(self, mock_popen):
        mock_popen.return_value = make_mock_popen(returncode=1, communicate_raise=True)
        result = run_with_timeout("/bin/true", 5, raise_on_timeout=False)
        self.assertNotEqual(result.returncode, 1)
        self.assertEqual(result.stdout, None)
        self.assertEqual(result.stderr, None)

    # kindly_end
    def test_kindly_end_terminates(self):
        mock_popen = make_mock_popen()
        kindly_end(mock_popen)
        mock_popen.terminate.assert_called()

    def test_kindly_end_kills_on_terminate_timeout(self):
        mock_popen = make_mock_popen(terminate_raise=True)
        kindly_end(mock_popen)
        mock_popen.terminate.assert_called()
        mock_popen.kill.assert_called()
