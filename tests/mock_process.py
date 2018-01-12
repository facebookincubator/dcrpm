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

from collections import namedtuple

from mock import create_autospec
import psutil

from dcrpm.util import TimeoutExpired

MockPopenFile = namedtuple('MockPopenFile', ['path'])


def make_mock_process(
    pid,
    open_files,
    name='',
    as_dict_throw=False,
    signal_throw=False,
    wait_throw=False,
    timeout=False,
):
    # type: (int, List[str], str, bool, bool, bool) -> psutil.Process
    """
    Creates a mock psutil.Process object suitable for these unit tests. If
    `throw` is True, it sets the side_effect of `as_dict` to throw a
    NoSuchProcess exception.
    """
    mock_process = create_autospec(psutil.Process)
    mock_process.pid = pid
    mock_process.name.return_value = name
    mock_process.as_dict.__name__ = 'as_dict'
    if as_dict_throw:
        mock_process.as_dict.side_effect = psutil.NoSuchProcess(pid)

    # This is hacky, but it works to simulate a TimeoutExpired actually being
    # raised by as_dict.
    elif timeout:
        mock_process.as_dict.side_effect = TimeoutExpired()
    else:
        mock_process.as_dict.return_value = {
            'pid': pid,
            'open_files': [MockPopenFile(f) for f in open_files],
        }
    if signal_throw:
        mock_process.send_signal.side_effect = psutil.NoSuchProcess(pid)
    else:
        mock_process.send_signal.return_value = None
    if wait_throw:
        mock_process.wait.side_effect = psutil.TimeoutExpired(5)
    else:
        mock_process.wait.return_value = None

    return mock_process
