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

import logging
import os

import psutil

from .util import TimeoutExpired, call_with_timeout

DEFAULT_TIMEOUT = 5  # seconds
MIN_PID = 2  # Don't kill init/launchd or kernel_task

logger = logging.getLogger()


def pids_holding_file(path):
    # type: str -> Set[psutil.Process]
    """
    Returns a list of pids holding open file `path`.
    """
    procs = set()
    for proc in psutil.process_iter():
        try:
            pinfo = call_with_timeout(
                proc.as_dict,
                DEFAULT_TIMEOUT,
                kwargs={'attrs': ['pid', 'open_files']},
            )
        except (psutil.NoSuchProcess, TimeoutExpired):
            continue

        # Sometimes open_files can be None.
        open_files = pinfo.get('open_files', [])
        if not open_files:
            continue

        if path in [f.path for f in open_files]:
            procs.add(proc)
    return procs


def pidfile_info(pidfile):
    # type: (str) -> Tuple[int, int]
    """
    Returns tuple of yum.pid pid and file mtime. Raises:
        FileNotFoundError if pidfile doesn't exist
        ValueError if pidfile doesn't look like a pid
        Something else that's bad and means we couldn't read it
    """
    with open(pidfile) as f:
        pid = int(f.read())
    if pid <= 1:
        # Negative PIDs lead to sadness
        # https://rachelbythebay.com/w/2014/08/19/fork/
        logger.error('Rejecting crazy pid value')
        raise ValueError('Invalid pid value')
    mtime = int(os.stat(pidfile).st_mtime)
    return (pid, mtime)


def send_signal(proc, sig, timeout=DEFAULT_TIMEOUT):
    # type: (psutil.Process, IntEnum, int) -> bool
    """
    Sends signal `sig` to process `proc`, waiting on each and handles timeouts
    as well as nonexistent pids. Returns whether pid was successfully sent
    signal.
    """
    # Don't accidentally signal core system processes.
    pid = proc.pid
    if pid < MIN_PID:
        logger.warning('Refusing to kill pid %d', pid)
        return False

    signame = str(sig).split('.')[-1]
    logger.info('Sending signal %s to pid %d', signame, pid)
    try:
        proc.send_signal(sig)
        proc.wait(timeout=timeout)
    except psutil.NoSuchProcess:
        logger.debug('Pid %d does not exist', pid)
        return False
    except psutil.TimeoutExpired:
        logger.debug('Timed out after %ds waiting for %d', timeout, pid)
        return False

    return True


def send_signals(procs, signal, timeout=DEFAULT_TIMEOUT):
    # type: (Iterable[psutil.Process], IntEnum, int) -> bool
    """
    Sends signal to all processes in `procs`. Returns whether anything was
    successfully signaled.
    """
    return any([send_signal(p, signal, timeout) for p in procs])


def process(pid):
    # type: (int) -> Optional[psutil.Process]
    """
    Thin wrapper around psutil.Process with exception handling, mainly for
    encapsulation.
    """
    try:
        return psutil.Process(pid)
    except psutil.NoSuchProcess:
        logging.error('Pid %d does not exist or is no longer active', pid)
        return None
