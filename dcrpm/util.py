#!/usr/bin/env python2
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
import signal
import subprocess

END_TIMEOUT = 5  # seconds

_logger = logging.getLogger()


class DcRPMException(Exception):
    """
    Exception to handle generic operation failures in dcrpm-py.
    """
    pass


class DBNeedsRecovery(DcRPMException):
    """
    Condition indicating the RPM DB needs to be recovered.
    """
    pass


class DBNeedsRebuild(DcRPMException):
    """
    Condition indicating the RPM DB needs to be rebuilt.
    """
    pass


class TimeoutExpired(Exception):
    """
    Simple exception shim indicating a subprocess timeout because Python 2
    doesn't have this.
    """
    pass


class CompletedProcess:
    """
    Shim for the fact that python2 doesn't have the CompletedProcess class for
    subprocesses.
    """

    def __init__(self, stdout='', stderr='', returncode=0):
        # type: (str, str, int) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class RepairAction:
    """
    Enum of different repair actions that dcrpm can perform. Used for
    classifying failures in a more programmatic fashion.
    """
    NO_ACTION = 0
    DB_RECOVERY = 1
    TABLE_REBUILD = 2
    KILL_LOCK_PIDS = 3
    STUCK_YUM = 4
    CLEAN_YUM_TRANSACTIONS = 5


class Result:
    """
    Enum representing whole program status.
    """
    OK = 0
    FAILED = 1


# Human readable names for different cleanup actions.
ACTION_NAMES = {
    RepairAction.NO_ACTION: 'no_action',
    RepairAction.DB_RECOVERY: 'db_recovery',
    RepairAction.TABLE_REBUILD: 'table_rebuild',
    RepairAction.KILL_LOCK_PIDS: 'kill_lock_pids',
    RepairAction.STUCK_YUM: 'stuck_yum',
    RepairAction.CLEAN_YUM_TRANSACTIONS: 'cleanup_yum_transactions',
}


def alarm_handler(signum, frame):
    # type: (int, Any) -> None
    """
    Alarm handler to pass to signal.signal for subprocess timeout.
    """
    raise TimeoutExpired()


def call_with_timeout(func, timeout, raise_=True, args=None, kwargs=None):
    # type: (Callable, int, bool, List[Any], Dict[str, Any]) -> Optional[Any]
    """
    A generic method that calls some callable and uses SIGALRM to time out the
    call should it take longer than `timeout`.
    If `raise_` is True, then it will raise a TimeoutExpired exception
    indicating the callable timed out. If `raise_` is False and the call times
    out, this function returns None.
    `args` is a list of arguments to pass to the callable (like *args)
    `kwargs` is a dict of keyword arguments to pass to the callable (like
    **kwargs)
    """
    if args is None:
        args = []
    if kwargs is None:
        kwargs = {}

    # Handle command timeouts.
    # from: https://stackoverflow.com/a/1191537
    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(timeout)
    output = None
    try:
        output = func(*args, **kwargs)
    except TimeoutExpired:
        if raise_:
            raise
    finally:
        signal.alarm(0)

    return output


def run_with_timeout(cmd, timeout, raise_on_nonzero=True):
    # type: (str, int, bool) -> CompletedProcess
    """
    Runs command `cmd` with timeout `timeout`. If `raise_on_nonzero` is True,
    raises a DcRPMException if `cmd` exits with a nonzero status.
    """
    _logger.debug('Running %s', cmd)
    cmdname = cmd.split()[0]
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = call_with_timeout(proc.communicate, timeout)
    except TimeoutExpired:
        msg = '%s timed out after %d' % (cmdname, timeout)
        _logger.error(msg)

        # Be nice about ending the process.
        _logger.info('Terminating %s', cmdname)
        kindly_end(proc)
        raise DcRPMException(msg)

    # Now get returncode.
    rc = proc.poll()
    if raise_on_nonzero and rc != 0:
        msg = '{} returned nonzero exit code ({})'.format(cmdname, rc)
        _logger.error(msg)
        raise DcRPMException(msg)

    return CompletedProcess(returncode=rc, stdout=stdout, stderr=stderr)


def kindly_end(proc, timeout=END_TIMEOUT):
    # type: (Popen, int) -> None
    """
    Tries to nicely end process `proc`, first by sending SIGTERM and then, if it
    still running, SIGKILL.
    """
    try:
        _logger.info('Sending SIGTERM to %d', proc.pid)
        proc.terminate()
        call_with_timeout(proc.wait, timeout)
    except TimeoutExpired:
        _logger.warning('Could not SIGTERM %d, sending SIGKILL', proc.pid)
        try:
            proc.kill()
            call_with_timeout(proc.wait, timeout)
        except TimeoutExpired:
            _logger.error('Could not SIGKILL %d, good luck', proc.pid)
