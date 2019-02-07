#!/usr/bin/env python
#
# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the GPLv2 license found in the LICENSE
# file in the root directory of this source tree.
#

from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import os

import psutil

from dcrpm.util import (
    DcRPMException,
    StatusCode,
    TimeoutExpired,
    run_with_timeout,
    which,
)


DEFAULT_TIMEOUT = 5  # seconds
LSOF_TIMEOUT = 60  # seconds (macOS `lsof` is slow)
MIN_PID = 2  # Don't kill init/launchd or kernel_task

logger = logging.getLogger()


def process(pid):
    # type: (int) -> Optional[psutil.Process]
    """
    Thin wrapper around psutil.Process with exception handling, mainly for
    encapsulation.
    """
    try:
        return psutil.Process(pid)
    except psutil.NoSuchProcess:
        logging.error("Pid %d does not exist or is no longer active", pid)
        return None


def _pids_holding_file(lsof, path):
    # type: (str, str) -> Set[int]
    try:
        cmd = "{} -F p {}".format(lsof, path)
        proc = run_with_timeout(cmd, LSOF_TIMEOUT, raise_on_nonzero=False)
    except DcRPMException:
        logger.warning("lsof timed out")
        return set()

    if proc.returncode != StatusCode.SUCCESS and proc.stderr:
        # `lsof` has pretty coarse error reporting. Returning nonzero means either
        # nothing matched or something went wrong. If nothing matches stderr will
        # be empty; if it contains output then assume something went wrong (though
        # "wrong" could be a fairly benign warning, like `path` not existing).
        logger.warning("lsof returned non-zero: %s", proc.stderr)

    return {int(line[1:]) for line in proc.stdout.splitlines() if line.startswith("p")}


def procs_holding_file(path):
    # type: str -> Set[psutil.Process]
    """
    Return a set of processes holding `path` open by using `lsof`. `lsof` is slower but
    will find processes that have other links to the same inode open.
    """
    lsof = which("lsof")
    if lsof is None:
        raise DcRPMException("Couldn't find `lsof` binary")

    procs = [process(pid) for pid in _pids_holding_file(lsof, path)]
    return set(filter(None, procs))


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
        logger.error("Rejecting crazy pid value")
        raise ValueError("Invalid pid value")
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
        logger.warning("Refusing to kill pid %d", pid)
        return False

    signame = str(sig).split(".")[-1]
    logger.info("Sending signal %s to pid %d", signame, pid)
    try:
        proc.send_signal(sig)
        proc.wait(timeout=timeout)
    except psutil.NoSuchProcess:
        logger.debug("Pid %d does not exist", pid)
        return False
    except psutil.TimeoutExpired:
        logger.debug("Timed out after %ds waiting for %d", timeout, pid)
        return False

    return True


def send_signals(procs, signal, timeout=DEFAULT_TIMEOUT):
    # type: (Iterable[psutil.Process], IntEnum, int) -> bool
    """
    Sends signal to all processes in `procs`. Returns whether anything was
    successfully signaled.
    """
    was_killed = [send_signal(p, signal, timeout) for p in procs]
    return any(was_killed)
