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

import signal
import sys
import typing as t
import unittest
from collections import namedtuple

from dcrpm import pidutil
from dcrpm.util import CompletedProcess, DcRPMException
from tests.mock_process import make_mock_process

if t.TYPE_CHECKING:
    import psutil


try:
    from unittest.mock import mock_open, patch
except ImportError:
    from mock import mock_open, patch


BASE = __name__ + ".pidutil"  # type: str
run_str = BASE + ".run_with_timeout"  # type: str

stat_result = t.NamedTuple("stat_result", [("st_mtime", int)])

if sys.version_info[0] == 2:
    # Python 2
    builtin_open = "__builtin__.open"  # type: str
else:
    # Python 3
    import builtins

    builtin_open = "builtins.open"  # type: str


class TestPidutil(unittest.TestCase):
    # procs_holding_file
    def test_procs_holding_file_no_lsof(self):
        # type: () -> None
        with patch("dcrpm.pidutil.which", return_value=None):
            with self.assertRaises(DcRPMException):
                pidutil.procs_holding_file("/tmp/foo")

    # _pids_holding_file
    def test__pids_holding_file_timeout(self):
        # type: () -> None
        with patch(run_str, side_effect=DcRPMException()):
            self.assertEqual(
                set(), pidutil._pids_holding_file("/path/to/lsof", "/tmp/foo")
            )

    def test__pids_holding_file_failed(self):
        # type: () -> None
        with patch(
            run_str, return_value=CompletedProcess(returncode=1, stderr="oh no")
        ):
            self.assertEqual(
                set(), pidutil._pids_holding_file("/path/to/lsof", "/tmp/foo")
            )

    def test__pids_holding_file_success(self):
        # type: () -> None
        lsof_stdout = "\n".join(["p12345", "f1", "p123456", "f1"])
        with patch(run_str, return_value=CompletedProcess(stdout=lsof_stdout)):
            self.assertEqual(
                set([12345, 123456]),
                pidutil._pids_holding_file("/path/to/lsof", "/tmp/a"),
            )

    # send_signal
    def test_send_signal_success(self):
        # type: () -> None
        proc = make_mock_process(12345, [])
        self.assertTrue(pidutil.send_signal(proc, signal.SIGKILL))

    def test_send_signal_no_such_process(self):
        # type: () -> None
        proc = make_mock_process(12345, [], signal_throw=True)
        self.assertFalse(pidutil.send_signal(proc, signal.SIGKILL))

    def test_send_signal_timeout(self):
        # type: () -> None
        proc = make_mock_process(12345, [], wait_throw=True)
        self.assertFalse(pidutil.send_signal(proc, signal.SIGKILL))

    # send_signals
    def test_send_signals_no_processes(self):
        # type: () -> None
        procs = []  # type: t.List[psutil.Process]
        self.assertFalse(pidutil.send_signals(procs, signal.SIGKILL))

    def test_send_signals_success(self):
        # type: () -> None
        procs = [
            make_mock_process(12345, ["/tmp/a", "/tmp/2"]),
            make_mock_process(54321, ["/tmp/1", "/tmp/3"]),
        ]  # type: t.List[psutil.Process]
        self.assertTrue(pidutil.send_signals(procs, signal.SIGKILL))
        self.assertEqual(sum(p.send_signal.call_count for p in procs), len(procs))

    def test_send_signals_signal_throws(self):
        # type: () -> None
        procs = [
            make_mock_process(12345, ["/tmp/a", "/tmp/2"], signal_throw=True),
            make_mock_process(54321, ["/tmp/1", "/tmp/3"]),
        ]  # type: t.List[psutil.Process]
        self.assertTrue(pidutil.send_signals(procs, signal.SIGKILL))
        self.assertEqual(sum(p.wait.call_count for p in procs), 1)

    def test_send_signals_wait_throws(self):
        # type: () -> None
        procs = [
            make_mock_process(12345, ["/tmp/a", "/tmp/2"], wait_throw=True),
            make_mock_process(54321, ["/tmp/1", "/tmp/3"]),
        ]  # type: t.List[psutil.Process]
        self.assertTrue(pidutil.send_signals(procs, signal.SIGKILL))

    def test_send_signals_all_throw(self):
        # type: () -> None
        procs = [
            make_mock_process(12345, ["/tmp/a", "/tmp/2"], signal_throw=True),
            make_mock_process(54321, ["/tmp/1", "/tmp/3"], wait_throw=True),
        ]  # type: t.List[psutil.Process]
        self.assertFalse(pidutil.send_signals(procs, signal.SIGKILL))

    # pidfile_info
    def test_pidfile_info_sucess(self):
        # type: () -> None
        with patch(builtin_open, mock_open(read_data="12345")) as mock_o, patch(
            "os.stat", return_value=stat_result(12345678)
        ):
            pid, _ = pidutil.pidfile_info("/some/path")
        self.assertEqual(pid, 12345)
        mock_o.assert_called_once_with("/some/path")

    def test_pidfile_info_bad_pid(self):
        # type: () -> None
        with patch(builtin_open, mock_open(read_data="-1")), patch(
            "os.stat", return_value=stat_result(12345678)
        ):
            with self.assertRaises(ValueError):
                pid, _ = pidutil.pidfile_info("/something")

    def test_pidfile_info_invalid_pid(self):
        # type: () -> None
        with patch(builtin_open, mock_open(read_data="ooglybogly")), patch(
            "os.stat", return_value=stat_result(12345678)
        ):
            with self.assertRaises(ValueError):
                pid, _ = pidutil.pidfile_info("/something")
