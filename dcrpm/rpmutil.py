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
import re
import signal
import sys
import time
import typing as t

import psutil

from .util import (
    CompletedProcess,
    DBIndexNeedsRebuild,
    DBNeedsRebuild,
    DBNeedsRecovery,
    DcRPMException,
    RepairAction,
    StatusCode,
    memoize,
    read_os_name,
    run_with_timeout,
)


RPM_CHECK_TIMEOUT_SEC = 5  # type: int
YUM_COMPLETE_TIMEOUT_SEC = 10  # type: int
VERIFY_TIMEOUT_SEC = 5  # type: int
RECOVER_TIMEOUT_SEC = 90  # type: int
REBUILD_TIMEOUT_SEC = 300  # type: int
MIN_ACCEPTABLE_PKG_COUNT = 50  # type: int


Check = t.Callable[[CompletedProcess], bool]


class RPMUtil:
    """
    Wraps operations around Berkeley DB and rpm tables.
    """

    def __init__(
        self,
        dbpath,  # type: str
        rpm_path,  # type: str
        recover_path,  # type: str
        verify_path,  # type: str
        stat_path,  # type: str
        yum_complete_transaction_path,  # type: str
        blacklist,  # type: t.List[str]
        forensic,  # type:  bool
    ):
        # type: (...) -> None
        self.dbpath = dbpath
        self.rpm_path = rpm_path
        self.recover_path = recover_path
        self.verify_path = verify_path
        self.stat_path = stat_path
        self.yum_complete_transaction_path = yum_complete_transaction_path
        self.blacklist = blacklist
        self.forensic = forensic
        self.logger = logging.getLogger()  # type: logging.Logger
        self.status_logger = logging.getLogger("status")  # type: logging.Logger
        self.populate_tables()

    def populate_tables(self):
        # type: () -> None
        """
        Populates self.tables. This is broken out from the constructor to
        support unit tests; the initial constructor is called with /tmp, but
        then the dbpath is changed (but the tables are never updated). This
        function will populate self.tables using whatever the dbpath is at call
        time.
        """
        self.tables = [
            table for table in os.listdir(self.dbpath) if str(table).istitle()
        ]  # type: t.List[str]

    def db_stat(self):
        # type: () -> None
        """
        Runs `db_stat -CA` which offers a view into the state of Berkeley DB
        environment.
        """
        try:
            ds = run_with_timeout(
                [self.stat_path, "-CA", "-h", self.dbpath],
                RPM_CHECK_TIMEOUT_SEC,
                raise_on_nonzero=False,
            )
            if ds.returncode > 0:
                # Sometimes db_stat can fail, let's try to preserve that
                debug = ds.stderr
            else:
                debug = ds.stdout
            self.status_logger.debug(debug, extra={"key": "db_stat"})
        except DcRPMException:
            # This is debug command, we're ignoring failures
            self.logger.error("db_stat -CA failed")

    def _poke_index(self, cmd, checks):
        # type: (t.Sequence[str], t.Iterable[Check]) -> None
        """
        Run cmd, and ensure all checks are True. Raise DBIndexNeedsRebuild otherwise
        """
        proc = run_with_timeout(cmd, RPM_CHECK_TIMEOUT_SEC, raise_on_nonzero=False)
        for check in checks:
            if not check(proc):
                raise DBIndexNeedsRebuild

    def check_rpmdb_indexes(self):
        # type: () -> None
        """
        For each rpmdb file we define a rpm command that blows up on inconsistencies,
        or returns incorrect results. Structure:
        'name_of_file': {
            'cmd': 'str', # rpm command
            'checks': [], # list of conditions to be met
        }
        """
        if sys.platform == "darwin":
            self.logger.debug("check_rpmdb_indexes is not implemented for darwin")
            return

        rpmdb_indexes = {
            "Basenames": {
                "cmd": [self.rpm_path, "-qf", self.rpm_path, "--dbpath", self.dbpath],
                "checks": [
                    lambda proc: proc.returncode != StatusCode.SEGFAULT,
                    lambda proc: len(proc.stdout.splitlines()) == 1,
                    lambda proc: proc.stdout.splitlines()[0].startswith("rpm-"),
                ],
            },
            "Conflictname": {
                "cmd": [
                    self.rpm_path,
                    "-q",
                    "--conflicts",
                    "setup",
                    "--dbpath",
                    self.dbpath,
                ],
                "checks": [
                    lambda proc: proc.returncode != StatusCode.SEGFAULT,
                    lambda proc: len(proc.stdout.splitlines()) == 3,
                ],
            },
            "Obsoletename": {
                "cmd": [
                    self.rpm_path,
                    "-q",
                    "--obsoletes",
                    "coreutils",
                    "--dbpath",
                    self.dbpath,
                ],
                "checks": [
                    lambda proc: proc.returncode != StatusCode.SEGFAULT,
                    lambda proc: len(proc.stdout.splitlines()) >= 1,
                ],
            },
            "Providename": {
                "cmd": [
                    self.rpm_path,
                    "-q",
                    "--whatprovides",
                    "rpm",
                    "--dbpath",
                    self.dbpath,
                ],
                "checks": [
                    lambda proc: proc.returncode != StatusCode.SEGFAULT,
                    lambda proc: len(proc.stdout.splitlines()) == 1,
                    lambda proc: proc.stdout.splitlines()[0].startswith("rpm-"),
                ],
            },
            "Requirename": {
                "cmd": [
                    self.rpm_path,
                    "-q",
                    "--whatrequires",
                    "rpm",
                    "--dbpath",
                    self.dbpath,
                ],
                "checks": [
                    lambda proc: proc.returncode != StatusCode.SEGFAULT,
                    lambda proc: len(proc.stdout.splitlines()) >= 1,
                    lambda proc: any(
                        line.startswith("rpm-") for line in proc.stdout.splitlines()
                    ),
                ],
            },
            "Recommendname": None,
            "Dirnames": None,
            "Group": None,
            "Name": None,
            "Installtid": None,
            "Enhancename": None,  # rarely used
            "Filetriggername": None,  # rarely used
            "Suggestname": None,  # rarely used
            "Supplementname": None,  # rarely used
            "Transfiletriggername": None,  # rarely used
            "Triggername": None,  # rarely used
        }  # type: t.Dict[str, t.Optional[t.Dict[str, t.Union[t.Sequence[str], t.Sequence[Check]]]]]

        # Checks for Packages db corruption
        post_checks = [
            lambda proc: not any(
                "cannot open Packages database" in line
                for line in proc.stderr.splitlines()
            ),
            lambda proc: any(
                "missing index" in line for line in proc.stderr.splitlines()
            ),
        ]

        for index, config in rpmdb_indexes.items():
            # Skip over indexes with no defined checks / conditions
            if not config:
                continue

            try:
                # Skip over non existing indexes
                if not os.path.join(self.dbpath, index):
                    self.logger.info("{} does not exist".format(index))
                    continue

                self.logger.info("Attempting to selectively poke at %s index", index)
                self._poke_index(
                    t.cast(t.List[str], config["cmd"]),
                    t.cast(t.List[Check], config["checks"]),
                )

            except DBIndexNeedsRebuild:
                self.status_logger.info(RepairAction.INDEX_REBUILD)
                index_path = os.path.join(self.dbpath, index)
                if os.path.isfile(index_path):
                    self.logger.info("%s index is out of whack, deleting it", index)
                    os.remove(index_path)
                else:
                    self.logger.info("%s index is missing", index)

                # Run the same command again, which should trigger a rebuild
                proc = run_with_timeout(
                    t.cast(t.List[str], config["cmd"]),
                    RPM_CHECK_TIMEOUT_SEC,
                    raise_on_nonzero=False,
                )

                # Sometimes single index rebuilds don't work, as rpm fails to
                # open Packages db. In that case we'll try a full recovery
                for check in post_checks:
                    if not check(proc):
                        self.logger.info("Granular index rebuild failed")
                        raise DBNeedsRecovery()

            except DcRPMException:
                self.logger.info("RPM commands are failing too hard")
                raise DBNeedsRecovery()

    def check_rpm_qa(self):
        # type: () -> None
        """
        Runs `rpm -qa` which serves as a good proxy check for whether bdb needs recovery
        """
        try:
            result = run_with_timeout(
                [self.rpm_path, "--dbpath", self.dbpath, "-qa"], RPM_CHECK_TIMEOUT_SEC
            )
        except DcRPMException:
            self.logger.error("rpm -qa failed")
            self.status_logger.warning("initial_db_check_fail")
            raise DBNeedsRecovery()

        packages = result.stdout.strip().split()
        # This test only makes sense on Linux; on macOS RPM is not the native
        # package manager, so a freshly-installed system can have
        # very few RPMs
        if read_os_name() == "Linux":
            if len(packages) < MIN_ACCEPTABLE_PKG_COUNT:
                self.logger.error(
                    "rpm package count seems too low; saw %d, expected at least %d",
                    len(packages),
                    MIN_ACCEPTABLE_PKG_COUNT,
                )
                raise DBNeedsRecovery()

        self.logger.debug("Package count: %d", len(packages))

    def query(self, rpm_name):
        # type: (str) -> None
        """
        The most basic sanity check, as `rpm -q $rpm_name` can return out of whack
        results (like 'perl' >.>)
        """
        try:
            result = run_with_timeout(
                [self.rpm_path, "--dbpath", self.dbpath, "-q", rpm_name],
                RPM_CHECK_TIMEOUT_SEC,
            )
            stdout = result.stdout.strip().split()
            if not len(stdout) == 1 or not stdout[0].startswith("{}-".format(rpm_name)):
                raise DBNeedsRebuild()
        except DBNeedsRebuild:
            raise
        except DcRPMException:
            self.logger.error("rpm -q %s failed", rpm_name)
            raise DBNeedsRecovery()

    def recover_db(self):
        # type: () -> None
        """
        Runs `db_recover`.
        """
        proc = run_with_timeout(
            [self.recover_path, "-h", self.dbpath],
            RECOVER_TIMEOUT_SEC,
            raise_on_nonzero=False,
        )
        # We've seen an unrecoverable failure mode where
        # db_recover segfaults, remediable only by a rebuild
        if proc.returncode != StatusCode.SUCCESS:
            self.status_logger.warning("db_recover_failed")
            if proc.returncode == StatusCode.SEGFAULT:
                raise DBNeedsRebuild
            else:
                raise DcRPMException(
                    "db_recover returned nonzero exit code ({}): {} {}".format(
                        proc.returncode, proc.stdout, proc.stderr
                    )
                )
        elif self.forensic:
            self.status_logger.debug(proc.stderr, extra={"key": "db_recover"})

    def rebuild_db(self):
        # type: () -> None
        """
        Runs `rpm --rebuilddb`.
        """
        try:
            run_with_timeout(
                [self.rpm_path, "--dbpath", self.dbpath, "--rebuilddb"],
                REBUILD_TIMEOUT_SEC,
            )
        except DcRPMException:
            self.status_logger.warning("rebuild_tables_failed")
            raise

    def check_tables(self):
        # type: () -> None
        """
        Runs the equivalent of:

          `rpm -qa --qf | sort | uniq | xargs rpm -q | grep 'is not installed$'`

        which checks each rpm in the DB to see if there are inconsistencies between what
        rpm thinks is installed and what is in the DB.
        """
        try:
            result = run_with_timeout(
                [self.rpm_path, "--dbpath", self.dbpath, "-qa", "--qf", "%{NAME}\\n"],
                timeout=RPM_CHECK_TIMEOUT_SEC,
                exception_to_raise=DBNeedsRebuild,
            )

            # Assume healthy if no RPMs listed.
            rpms = sorted(set(result.stdout.splitlines()))
            if not rpms:
                return
            result = run_with_timeout(
                [self.rpm_path, "--dbpath", self.dbpath, "-q"] + rpms,
                timeout=RPM_CHECK_TIMEOUT_SEC,
                exception_to_raise=DBNeedsRebuild,
            )

        except DcRPMException as e:
            self.status_logger.warning("initial_table_check_fail")
            raise

        lines = result.stdout.splitlines()
        if any([line.endswith("is not installed") for line in lines]):
            raise DBNeedsRebuild()

    def verify_tables(self):
        # type: () -> None
        """
        Runs `db_verify` on all rpmdb tables.
        """
        for table in self.tables:
            if os.path.basename(table) in self.blacklist:
                self.logger.warning("Skipping table '%s', blacklisted", table)
                continue

            try:
                result = run_with_timeout(
                    [self.verify_path, os.path.join(self.dbpath, table)],
                    VERIFY_TIMEOUT_SEC,
                    raise_on_nonzero=False,
                )
            except DcRPMException:
                self.status_logger.warning("initial_table_verify_fail")
                raise

            # This raises a DcRPMException because it gets handled specially in
            # the main run loop.
            if result.returncode != 0:
                self.logger.error("db_verify returned nonzero status")
                raise DcRPMException()

    def clean_yum_transactions(self):
        # type: () -> None
        """
        Runs yum-complete-transaction.
        """
        self.status_logger.info(RepairAction.CLEAN_YUM_TRANSACTIONS)
        run_with_timeout(
            [self.yum_complete_transaction_path, "--cleanup"],
            YUM_COMPLETE_TIMEOUT_SEC,
            raise_on_nonzero=False,
            raise_on_timeout=False,
        )

    def kill_spinning_rpm_query_processes(
        self, kill_after_seconds=3600, kill_timeout=5
    ):
        # type: (int, int) -> None
        """
        Find and kill any rpm query processes over an hour old by looking explicitly for
        `rpm -q`.
        """
        for proc in psutil.process_iter():
            try:
                cmd = proc.cmdline()
                # Valid command
                if not cmd or len(cmd) < 2:
                    continue
                # Looks like rpm
                if not (re.match(r"(/(usr/)?bin/)?rpm", cmd[0]) and "-q" in cmd):
                    continue

                self.logger.info("Considering pid %s", proc.pid)
                ctime = proc.create_time()

                if time.time() - ctime > kill_after_seconds:
                    self.logger.error(
                        "Found stale rpm process: (%d) %s", proc.pid, " ".join(cmd)
                    )
                    proc.send_signal(signal.SIGKILL)
                    proc.wait(timeout=kill_timeout)

            except psutil.NoSuchProcess:
                self.logger.warning("Skipping pid %d, it disappeared", proc.pid)
                continue
            except psutil.AccessDenied:
                self.logger.warning("Skipping pid %d, cannot access it", proc.pid)
                continue
            except psutil.TimeoutExpired:
                self.logger.warning(
                    "Timed out after %ds waiting for pid %d", kill_timeout, proc.pid
                )

    def _get_macros(self):
        # type: () -> t.Dict[str, str]
        result = run_with_timeout(
            [self.rpm_path, "--dbpath", self.dbpath, "--showrc"],
            timeout=RPM_CHECK_TIMEOUT_SEC,
        )
        macros = {}  # type: t.Dict[str, str]
        for line in result.stdout.splitlines():
            # TODO: make this parse multi-line macros properly
            m = re.match(r"^-\d+:\s+(\w+)\s+([\w\s]+)$", line)
            if m:
                key = m.group(1)
                val = m.group(2)
                if key and val:
                    macros[key] = val

        self.logger.debug("RPM macros = %s" % macros)
        return macros

    def get_db_backend(self):
        # type: () -> str
        macros = self._get_macros()
        if "_db_backend" in macros:
            return macros["_db_backend"]
        else:
            self.logger.warning("No db_backend found in macros, assuming bdb")
            return "bdb"
