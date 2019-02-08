#!/usr/bin/env python
#
# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the GPLv2 license found in the LICENSE
# file in the root directory of this source tree.
#

from __future__ import absolute_import, division, print_function, unicode_literals

import signal
import sys
import unittest
from collections import namedtuple

try:
    from unittest.mock import mock_open, patch
except ImportError:
    from mock import mock_open, patch

from dcrpm import pidutil
from tests.mock_process import make_mock_process


stat_result = namedtuple("stat_result", ["st_mtime"])

if sys.version_info[0] == 2:
    # Python 2
    builtin_open = "__builtin__.open"
else:
    # Python 3
    import builtins

    builtin_open = "builtins.open"


class TestPidutil(unittest.TestCase):
    # procs_holding_file
    def test_procs_holding_file_none(self):
        procs = [
            make_mock_process(12345, ["/tmp/1", "/tmp/2"]),
            make_mock_process(54321, ["/tmp/1", "/tmp/3"]),
        ]
        with patch("psutil.process_iter", return_value=procs):
            pids = pidutil.procs_holding_file("/tmp/a")
        self.assertEqual(len(pids), 0)

    def test_procs_holding_file_some(self):
        procs = [
            make_mock_process(12345, ["/tmp/a", "/tmp/2"]),
            make_mock_process(54321, ["/tmp/1", "/tmp/3"]),
        ]
        with patch("psutil.process_iter", return_value=procs):
            procs = pidutil.procs_holding_file("/tmp/a")
            self.assertEqual(len(procs), 1)

    def test_procs_holding_file_no_process(self):
        procs = [
            # throw only on the one that would match.
            make_mock_process(12345, ["/tmp/a", "/tmp/2"], as_dict_throw=True),
            make_mock_process(54321, ["/tmp/1", "/tmp/3"]),
        ]
        with patch("psutil.process_iter", return_value=procs):
            procs = pidutil.procs_holding_file("/tmp/a")
        self.assertEqual(len(procs), 0)

    def test_procs_holding_file_timeout(self):
        procs = [
            make_mock_process(12345, ["/tmp/a", "/tmp/2"]),
            make_mock_process(54321, ["/tmp/1", "/tmp/3"]),
            make_mock_process(12346, ["/tmp/a", "/tmp/3"], timeout=True),
        ]
        with patch("psutil.process_iter", return_value=procs):
            procs = pidutil.procs_holding_file("/tmp/a")
            self.assertEqual(len(procs), 1)

    # send_signal
    def test_send_signal_success(self):
        proc = make_mock_process(12345, [])
        self.assertTrue(pidutil.send_signal(proc, signal.SIGKILL))

    def test_send_signal_no_such_process(self):
        proc = make_mock_process(12345, [], signal_throw=True)
        self.assertFalse(pidutil.send_signal(proc, signal.SIGKILL))

    def test_send_signal_timeout(self):
        proc = make_mock_process(12345, [], wait_throw=True)
        self.assertFalse(pidutil.send_signal(proc, signal.SIGKILL))

    # send_signals
    def test_send_signals_no_processes(self):
        procs = []
        self.assertFalse(pidutil.send_signals(procs, signal.SIGKILL))

    def test_send_signals_success(self):
        procs = [
            make_mock_process(12345, ["/tmp/a", "/tmp/2"]),
            make_mock_process(54321, ["/tmp/1", "/tmp/3"]),
        ]
        self.assertTrue(pidutil.send_signals(procs, signal.SIGKILL))
        self.assertEqual(sum(p.send_signal.call_count for p in procs), len(procs))

    def test_send_signals_signal_throws(self):
        procs = [
            make_mock_process(12345, ["/tmp/a", "/tmp/2"], signal_throw=True),
            make_mock_process(54321, ["/tmp/1", "/tmp/3"]),
        ]
        self.assertTrue(pidutil.send_signals(procs, signal.SIGKILL))
        self.assertEqual(sum(p.wait.call_count for p in procs), 1)

    def test_send_signals_wait_throws(self):
        procs = [
            make_mock_process(12345, ["/tmp/a", "/tmp/2"], wait_throw=True),
            make_mock_process(54321, ["/tmp/1", "/tmp/3"]),
        ]
        self.assertTrue(pidutil.send_signals(procs, signal.SIGKILL))

    def test_send_signals_all_throw(self):
        procs = [
            make_mock_process(12345, ["/tmp/a", "/tmp/2"], signal_throw=True),
            make_mock_process(54321, ["/tmp/1", "/tmp/3"], wait_throw=True),
        ]
        self.assertFalse(pidutil.send_signals(procs, signal.SIGKILL))

    # pidfile_info
    def test_pidfile_info_sucess(self):
        with patch(builtin_open, mock_open(read_data="12345")) as mock_o, patch(
            "os.stat", return_value=stat_result("12345678")
        ):
            pid, _ = pidutil.pidfile_info("/some/path")
        self.assertEqual(pid, 12345)
        mock_o.assert_called_once_with("/some/path")

    def test_pidfile_info_bad_pid(self):
        with patch(builtin_open, mock_open(read_data="-1")), patch(
            "os.stat", return_value=stat_result("12345678")
        ):
            with self.assertRaises(ValueError):
                pid, _ = pidutil.pidfile_info("/something")

    def test_pidfile_info_invalid_pid(self):
        with patch(builtin_open, mock_open(read_data="ooglybogly")), patch(
            "os.stat", return_value=stat_result("12345678")
        ):
            with self.assertRaises(ValueError):
                pid, _ = pidutil.pidfile_info("/something")
