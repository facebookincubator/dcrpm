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

import math
from mock import Mock, call, patch
import signal
import subprocess
import time
import unittest

from dcrpm.util import (
    DcRPMException,
    TimeoutExpired,
    alarm_handler,
    call_with_timeout,
    run_with_timeout,
)

call_str = __name__ + '.call_with_timeout'


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
        'communicate.__name__': 'communicate',
        'poll.return_value': returncode,
    }
    if communicate_raise:
        del config['communicate.return_value']
        config['communicate.side_effect'] = TimeoutExpired()
    mock_popen.configure_mock(**config)
    return mock_popen


class TestUtil(unittest.TestCase):
    def setUp(self):
        pass

    # call_with_timeout
    @patch('signal.signal')
    @patch('signal.alarm')
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
    @patch(call_str)
    @patch('subprocess.Popen', return_value=make_mock_popen())
    def test_run_with_timeout_success(self, mock_popen, mock_call):
        result = run_with_timeout('/bin/true', 5)
        self.assertEqual(result.returncode, 0)
        mock_popen.assert_called_once_with(
            '/bin/true',
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    @patch(call_str)
    @patch(
        'subprocess.Popen',
        return_value=make_mock_popen(returncode=1, communicate_raise=True),
    )
    def test_run_with_timeout_timeout(self, mock_popen, mock_call):
        with self.assertRaises(DcRPMException):
            run_with_timeout('/bin/true', 5)

    @patch(call_str)
    @patch('subprocess.Popen', return_value=make_mock_popen(returncode=1))
    def test_run_with_timeout_raise_on_nonzero(self, mock_popen, mock_call):
        with self.assertRaises(DcRPMException):
            run_with_timeout('/bin/true', 5)

    @patch(call_str)
    @patch('subprocess.Popen', return_value=make_mock_popen(returncode=1))
    def test_run_with_timeout_no_raise_on_nonzero(self, mock_popen, mock_call):
        result = run_with_timeout('/bin/true', 5, raise_on_nonzero=False)
        self.assertEqual(result.returncode, 1)
