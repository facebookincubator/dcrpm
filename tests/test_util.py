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

import math
import signal
import subprocess
import time
import typing as t  # noqa

import testslide
from dcrpm.util import (
    DcRPMException,
    TimeoutExpired,
    alarm_handler,
    call_with_timeout,
    kindly_end,
    run_with_timeout,
)


try:
    from unittest.mock import Mock
except ImportError:
    from mock import Mock


def make_mock_popen(
    stdout="",  # type: str
    stderr="",  # type: str
    returncode=0,  # type: int
    communicate_raise=False,  # type: bool
    terminate_raise=False,  # type: bool
):
    # type: (...) -> Mock
    """
    Creates a simple mocked Popen object that responds to Popen.poll and
    Popen.communicate.
    """
    mock_popen_obj = Mock()
    config = {"poll.return_value": returncode}  # type: t.Dict[str, t.Any]
    if communicate_raise:
        config["communicate.side_effect"] = TimeoutExpired()
    else:
        config["communicate.return_value"] = (stdout, stderr)
    if terminate_raise:
        config["terminate.side_effect"] = TimeoutExpired()
    mock_popen_obj.configure_mock(**config)
    return mock_popen_obj


class TestUtil(testslide.TestCase):
    # call_with_timeout
    def test_call_with_timeout_success(self):
        # type: () -> None
        (
            self.mock_callable(signal, "signal")
            .for_call(signal.SIGALRM, alarm_handler)
            .to_return_value(None)
            .and_assert_called_once()
        )
        for val in [2, 0]:
            (
                self.mock_callable(signal, "alarm")
                .for_call(val)
                .to_return_value(None)
                .and_assert_called_once()
            )
        result = call_with_timeout(math.floor, 2, args=[2.5])
        self.assertEqual(result, 2.0)

    def test_call_with_timeout_real_raises(self):
        # type: () -> None
        with self.assertRaises(TimeoutExpired):
            call_with_timeout(time.sleep, 1, args=[2])

    # run_with_timeout
    def test_run_with_timeout_success(self):
        # type: () -> None
        (
            self.mock_callable(subprocess, "Popen")
            .for_call(
                ["/bin/true"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            .to_return_value(make_mock_popen())
            .and_assert_called_once()
        )
        result = run_with_timeout(["/bin/true"], 5)
        self.assertEqual(result.returncode, 0)

    def test_run_with_timeout_timeout(self):
        # type: () -> None
        mock_popen = make_mock_popen(communicate_raise=True)
        (
            self.mock_callable(subprocess, "Popen")
            .for_call(
                ["/bin/true"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            .to_return_value(mock_popen)
            .and_assert_called_once()
        )
        with self.assertRaises(DcRPMException):
            run_with_timeout(["/bin/true"], 5)
        mock_popen.kill.assert_not_called()

    def test_run_with_timeout_terminates_on_timeout(self):
        # type: () -> None
        mock_popen = make_mock_popen(communicate_raise=True)
        (
            self.mock_callable(subprocess, "Popen")
            .for_call(
                ["/bin/true"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            .to_return_value(mock_popen)
            .and_assert_called_once()
        )
        with self.assertRaises(DcRPMException):
            run_with_timeout(["/bin/true"], 5)
        mock_popen.terminate.assert_called()
        mock_popen.kill.assert_not_called()

    def test_run_with_timeout_kills_on_terminate_timeout(self):
        # type: () -> None
        mock_popen = make_mock_popen(communicate_raise=True, terminate_raise=True)
        (
            self.mock_callable(subprocess, "Popen")
            .for_call(
                ["/bin/true"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            .to_return_value(mock_popen)
            .and_assert_called_once()
        )
        with self.assertRaises(DcRPMException):
            run_with_timeout(["/bin/true"], 5)
        mock_popen.terminate.assert_called()
        mock_popen.kill.assert_called()

    def test_run_with_timeout_raise_on_nonzero(self):
        # type: () -> None
        (
            self.mock_callable(subprocess, "Popen")
            .for_call(
                ["/bin/true"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            .to_return_value(make_mock_popen(returncode=1))
            .and_assert_called_once()
        )
        with self.assertRaises(DcRPMException):
            run_with_timeout(["/bin/true"], 5)

    def test_run_with_timeout_no_raise_on_nonzero(self):
        # type: () -> None
        (
            self.mock_callable(subprocess, "Popen")
            .for_call(
                ["/bin/true"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            .to_return_value(make_mock_popen(returncode=1))
            .and_assert_called_once()
        )
        result = run_with_timeout(["/bin/true"], 5, raise_on_nonzero=False)
        self.assertEqual(result.returncode, 1)

    def test_run_with_timeout_no_raise_on_timeout(self):
        # type: () -> None
        mock_popen = make_mock_popen(returncode=1, communicate_raise=True)
        (
            self.mock_callable(subprocess, "Popen")
            .for_call(
                ["/bin/true"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            .to_return_value(mock_popen)
            .and_assert_called_once()
        )
        result = run_with_timeout(["/bin/true"], 5, raise_on_timeout=False)
        self.assertNotEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    # kindly_end
    def test_kindly_end_terminates(self):
        # type: () -> None
        mock_popen = make_mock_popen()
        kindly_end(mock_popen)
        mock_popen.terminate.assert_called()

    def test_kindly_end_kills_on_terminate_timeout(self):
        # type: () -> None
        mock_popen = make_mock_popen(terminate_raise=True)
        kindly_end(mock_popen)
        mock_popen.terminate.assert_called()
        mock_popen.kill.assert_called()
