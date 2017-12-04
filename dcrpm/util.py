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
