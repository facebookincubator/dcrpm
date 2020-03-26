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

import logging
import os
import signal
import subprocess
import typing as t


if t.TYPE_CHECKING:
    from types import FrameType


END_TIMEOUT = 5  # type: int

_logger = logging.getLogger()  # type: logging.Logger

# Generic ReturnType
RT = t.TypeVar("RT")


class StatusCode:
    """
    Command return codes codified
    """

    SUCCESS = 0  # type: int
    SEGFAULT = -11  # type: int


class DcRPMException(Exception):
    """
    Exception to handle generic operation failures in dcrpm-py.
    """


class DBNeedsRecovery(DcRPMException):
    """
    Condition indicating the RPM DB needs to be recovered.
    """


class DBIndexNeedsRebuild(DcRPMException):
    """
    Single BDB index might need a rebuild
    """


class DBNeedsRebuild(DcRPMException):
    """
    Condition indicating the RPM DB needs to be rebuilt.
    """


class TimeoutExpired(Exception):
    """
    Simple exception shim indicating a subprocess timeout because Python 2
    doesn't have this.
    """


class CompletedProcess:
    """
    Shim for the fact that python2 doesn't have the CompletedProcess class for
    subprocesses.
    """

    def __init__(self, stdout="", stderr="", returncode=0):
        # type: (str, str, int) -> None
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class RepairAction:
    """
    Enum of different repair actions that dcrpm can perform. Used for
    classifying failures in a more programmatic fashion.
    """

    NO_ACTION = 0  # type: int
    DB_RECOVERY = 1  # type: int
    TABLE_REBUILD = 2  # type: int
    KILL_LOCK_PIDS = 3  # type: int
    STUCK_YUM = 4  # type: int
    CLEAN_YUM_TRANSACTIONS = 5  # type: int
    INDEX_REBUILD = 6  # type: int
    KILL_DB001_PIDS = 7  # type: int


class Result:
    """
    Enum representing whole program status.
    """

    OK = 0  # type: int
    FAILED = 1  # type: int


# Human readable names for different cleanup actions.
ACTION_NAMES = {
    RepairAction.NO_ACTION: "no_action",
    RepairAction.DB_RECOVERY: "db_recovery",
    RepairAction.TABLE_REBUILD: "table_rebuild",
    RepairAction.KILL_DB001_PIDS: "kill_db001_pids",
    RepairAction.KILL_LOCK_PIDS: "kill_lock_pids",
    RepairAction.STUCK_YUM: "stuck_yum",
    RepairAction.CLEAN_YUM_TRANSACTIONS: "cleanup_yum_transactions",
    RepairAction.INDEX_REBUILD: "index_rebuild",
}  # type: t.Dict[int, str]


def memoize(f):
    # type: (t.Callable[..., RT]) -> t.Callable[..., RT]
    cache = {}  # type: t.Dict[str, RT]

    # pyre-ignore[2]: *args and **kwargs
    def wrapper(*args, **kwargs):
        # type: (t.Any, t.Any) -> RT
        key = str(args) + str(kwargs)
        if key not in cache:
            cache[key] = f(*args, **kwargs)
        return cache[key]

    return wrapper


def alarm_handler(signum, frame):
    # type: (int, FrameType) -> None
    """
    Alarm handler to pass to signal.signal for subprocess timeout.
    """
    raise TimeoutExpired()


def call_with_timeout(
    func,  # type: t.Callable[..., RT]
    timeout,  # type: int
    args=None,  # type: t.Optional[t.Iterable[str]]
    # pyre-ignore[2]: kwargs has type dict[str, Any]
    kwargs=None,  # type: t.Optional[t.Dict[str, t.Any]]
):
    # type: (...) -> RT
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
    try:
        return func(*args, **kwargs)
    finally:
        signal.alarm(0)

    raise DcRPMException("should not get here")


def run_with_timeout(
    cmd,  # type: t.Sequence[str]
    timeout,  # type: int
    raise_on_nonzero=True,  # type: bool
    raise_on_timeout=True,  # type: bool
    exception_to_raise=DcRPMException,  # type: t.Type[Exception]
):
    # type: (...) -> CompletedProcess
    """
    Runs command `cmd` with timeout `timeout`. If `raise_on_nonzero` is True,
    raises a DcRPMException if `cmd` exits with a nonzero status. If
    `raise_on_timeout` is true, raises a DcRPMException if `cmd` times out.
    """
    if not cmd:
        raise ValueError("must pass command to run")

    _logger.debug("Running %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
    )
    try:
        stdout, stderr = call_with_timeout(proc.communicate, timeout)
    except TimeoutExpired:
        msg = "%s timed out after %d" % (cmd[0], timeout)
        _logger.error(msg)

        # Be nice about ending the process.
        _logger.info("Terminating %s", cmd[0])
        rc = kindly_end(proc)
        if raise_on_timeout:
            raise exception_to_raise(msg)
        return CompletedProcess(returncode=rc, stdout="", stderr="")

    # Now get returncode.
    rc = proc.poll()
    if raise_on_nonzero and rc != 0:
        msg = "{} returned nonzero exit code ({})".format(cmd[0], rc)
        _logger.error(msg)
        raise exception_to_raise(msg)

    return CompletedProcess(returncode=rc, stdout=stdout, stderr=stderr)


def kindly_end(proc, timeout=END_TIMEOUT):
    # type: (subprocess.Popen, int) -> int
    """
    Tries to nicely end process `proc`, first by sending SIGTERM and then, if it
    is still running, SIGKILL.
    """
    rc = 1  # type: t.Optional[int]
    try:
        _logger.info("Sending SIGTERM to %d", proc.pid)
        proc.terminate()
        rc = call_with_timeout(proc.wait, timeout)
    except TimeoutExpired:
        _logger.warning("Could not SIGTERM %d, sending SIGKILL", proc.pid)
        try:
            proc.kill()
            rc = call_with_timeout(proc.wait, timeout)
        except TimeoutExpired:
            _logger.error("Could not SIGKILL %d, good luck", proc.pid)

    return rc if rc else 1


@memoize
def which(cmd):
    # type: (str) -> str
    try:
        import shutil

        path = shutil.which(cmd)
        if not path:
            raise DcRPMException("failed to find '{}'".format(cmd))
        return path
    except AttributeError:
        for path in os.environ["PATH"].split(os.pathsep):
            p = os.path.join(path, cmd)
            if os.access(p, os.X_OK):
                return p

    raise DcRPMException("could not find '{}' in $PATH".format(cmd))


@memoize
def read_os_name():
    # type: () -> str
    """
    Call platform.system() and caches the value
    """
    import platform

    return platform.system()


@memoize
def read_os_release():
    # type: () -> t.Dict[str, str]
    """
    Read /etc/os-release (if it exists) and parse the key/value data into
    a dict.
    """
    data = {}
    if os.path.exists("/etc/os-release"):
        with open("/etc/os-release", "r") as f:
            for line in f:
                if line.strip() == "":
                    continue
                (key, value) = line.split("=", 2)
                data[key.strip()] = value.strip()

    return data
