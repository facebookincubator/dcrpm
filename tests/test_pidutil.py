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

import os
import signal
import sys
import typing as t

import testslide
from dcrpm import pidutil
from dcrpm.util import CompletedProcess, DcRPMException
from tests.mock_process import make_mock_process


if t.TYPE_CHECKING:
    import psutil

try:
    from unittest.mock import mock_open
except ImportError:
    from mock import mock_open


if sys.version_info[0] == 2:
    builtins = "__builtin__"
else:
    import builtins


stat_result = t.NamedTuple("stat_result", [("st_mtime", int)])


class TestPidutil(testslide.TestCase):
    # procs_holding_file
    def test_procs_holding_file_no_lsof(self):
        # type: () -> None
        (
            self.mock_callable(pidutil, "which")
            .to_return_value(None)
            .and_assert_called_once()
        )
        with self.assertRaises(DcRPMException):
            pidutil.procs_holding_file("/tmp/foo")

    # _pids_holding_file
    def test__pids_holding_file_timeout(self):
        # type: () -> None
        (
            self.mock_callable(pidutil, "run_with_timeout")
            .to_raise(DcRPMException())
            .and_assert_called_once
        )
        self.assertFalse(pidutil._pids_holding_file("/path/to/lsof", "/tmp/foo"))

    def test__pids_holding_file_failed(self):
        # type: () -> None
        (
            self.mock_callable(pidutil, "run_with_timeout")
            .to_return_value(CompletedProcess(returncode=1, stderr="oh no"))
            .and_assert_called_once
        )
        self.assertFalse(pidutil._pids_holding_file("/path/to/lsof", "/tmp/foo"))

    def test__pids_holding_file_success(self):
        # type: () -> None
        (
            self.mock_callable(pidutil, "run_with_timeout")
            .to_return_value(
                CompletedProcess(stdout="\n".join(["p12345", "f1", "p123456", "f1"]))
            )
            .and_assert_called_once
        )
        self.assertEqual(
            set([12345, 123456]), pidutil._pids_holding_file("/path/to/lsof", "/tmp/a")
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


class TestPidfileInfo(testslide.TestCase):
    def setUp(self):
        # type: () -> None
        super(TestPidfileInfo, self).setUp()
        self.mock_callable(builtins, "open").to_call_original()
        self.mock_callable(os, "stat").to_call_original()

    def test_pidfile_info_sucess(self):
        # type: () -> None
        (
            self.mock_callable(builtins, "open")
            .for_call("/some/path")
            .with_implementation(mock_open(read_data="12345"))
            .and_assert_called_once()
        )
        (
            self.mock_callable(os, "stat")
            .for_call("/some/path")
            .to_return_value(stat_result(12345678))
            .and_assert_called_once()
        )
        pid, _ = pidutil.pidfile_info("/some/path")
        self.assertEqual(pid, 12345)

    def test_pidfile_info_bad_pid(self):
        # type: () -> None
        (
            self.mock_callable(builtins, "open")
            .for_call("/something")
            .with_implementation(mock_open(read_data="-1"))
            .and_assert_called_once()
        )
        self.mock_callable(os, "stat").and_assert_not_called()
        with self.assertRaises(ValueError):
            pid, _ = pidutil.pidfile_info("/something")

    def test_pidfile_info_invalid_pid(self):
        # type: () -> None
        (
            self.mock_callable(builtins, "open")
            .for_call("/something")
            .with_implementation(mock_open(read_data="ooglybogly"))
            .and_assert_called_once()
        )
        self.mock_callable(os, "stat").and_assert_not_called()
        with self.assertRaises(ValueError):
            pid, _ = pidutil.pidfile_info("/something")
