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
import re
import signal
import sys
import time

import psutil

from .util import (
    DBIndexNeedsRebuild,
    DBNeedsRebuild,
    DBNeedsRecovery,
    DcRPMException,
    RepairAction,
    StatusCode,
    memoize,
    run_with_timeout,
)


RPM_CHECK_TIMEOUT_SEC = 5
YUM_COMPLETE_TIMEOUT_SEC = 10
VERIFY_TIMEOUT_SEC = 5
RECOVER_TIMEOUT_SEC = 90
REBUILD_TIMEOUT_SEC = 300
MIN_ACCEPTABLE_PKG_COUNT = 50


class RPMUtil:
    """
    Wraps operations around Berkeley DB and rpm tables.
    """

    def __init__(
        self,
        dbpath,
        rpm_path,
        recover_path,
        verify_path,
        stat_path,
        yum_complete_transaction_path,
        blacklist,
        forensic,
    ):
        # type: (str, str, str, str, List[str]) -> None
        self.dbpath = dbpath
        self.rpm_path = rpm_path
        self.recover_path = recover_path
        self.verify_path = verify_path
        self.stat_path = stat_path
        self.yum_complete_transaction_path = yum_complete_transaction_path
        self.blacklist = blacklist
        self.forensic = forensic
        self.logger = logging.getLogger()
        self.status_logger = logging.getLogger("status")
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
        self.tables = [t for t in os.listdir(self.dbpath) if str(t).istitle()]

    def db_stat(self):
        # type: () -> None
        """
        Runs `db_stat -CA` which offers a view into the state of Berkeley DB
        environment.
        """
        try:
            cmd = "{} -CA -h {}".format(self.stat_path, self.dbpath)
            ds = run_with_timeout(cmd, RPM_CHECK_TIMEOUT_SEC, raise_on_nonzero=False)
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
        """
        Run cmd, and ensure all checks are True. Raise DBIndexNeedsRebuild otherwise
        """
        proc = run_with_timeout(cmd, RPM_CHECK_TIMEOUT_SEC, raise_on_nonzero=False)
        for check in checks:
            if not check(proc):
                raise DBIndexNeedsRebuild

    @memoize
    def _read_os_release(self):
        # type: () -> Dict[str, str]
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
                "cmd": "{} -qf {} --dbpath {}".format(
                    self.rpm_path, self.rpm_path, self.dbpath
                ),
                "checks": [
                    lambda proc: proc.returncode != StatusCode.SEGFAULT,
                    lambda proc: len(proc.stdout.splitlines()) == 1,
                    lambda proc: proc.stdout.splitlines()[0].startswith("rpm-"),
                ],
            },
            "Conflictname": {
                "cmd": "{} -q --conflicts initscripts --dbpath {}".format(
                    self.rpm_path, self.dbpath
                ),
                "checks": [
                    lambda proc: proc.returncode != StatusCode.SEGFAULT,
                    lambda proc: len(proc.stdout.splitlines()) > 3,
                ],
            },
            "Obsoletename": {
                "cmd": "{} -q --obsoletes coreutils --dbpath {}".format(
                    self.rpm_path, self.dbpath
                ),
                "checks": [
                    lambda proc: proc.returncode != StatusCode.SEGFAULT,
                    lambda proc: len(proc.stdout.splitlines()) > 2,
                ],
            },
            "Providename": {
                "cmd": "{} -q --whatprovides rpm --dbpath {}".format(
                    self.rpm_path, self.dbpath
                ),
                "checks": [
                    lambda proc: proc.returncode != StatusCode.SEGFAULT,
                    lambda proc: len(proc.stdout.splitlines()) == 1,
                    lambda proc: proc.stdout.splitlines()[0].startswith("rpm-"),
                ],
            },
            "Requirename": {
                "cmd": "{} -q --whatrequires rpm --dbpath {}".format(
                    self.rpm_path, self.dbpath
                ),
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
        }

        # For some platforms, the command and/or checks need to be tweaked
        os_release_data = self._read_os_release()
        os_id = os_release_data.get("ID", "")
        if os_id == "fedora":
            # Fedora has two differences from CentOS:
            # - For Conflictname, initscripts is installed, but no capabilities
            #   conflict with it. systemd is another mandatory core package
            #   which does have capabilities which conflict with it, but it only
            #   has two (as of Fedora 28/29).
            # - For Obsoletename, coreutils only obsoletes older versions of
            #   itself.
            rpmdb_indexes.update(
                {
                    "Conflictname": {
                        "cmd": "{} -q --conflicts systemd --dbpath {}".format(
                            self.rpm_path, self.dbpath
                        ),
                        "checks": [
                            lambda proc: proc.returncode != StatusCode.SEGFAULT,
                            lambda proc: len(proc.stdout.splitlines()) >= 2,
                        ],
                    },
                    "Obsoletename": {
                        "cmd": "{} -q --obsoletes coreutils --dbpath {}".format(
                            self.rpm_path, self.dbpath
                        ),
                        "checks": [
                            lambda proc: proc.returncode != StatusCode.SEGFAULT,
                            lambda proc: len(proc.stdout.splitlines()) >= 1,
                        ],
                    },
                }
            )

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
            try:
                # Skip over non existing indexes
                if not os.path.join(self.dbpath, index):
                    self.logger.info("{} does not exist".format(index))
                    continue

                # Skip over indexes with no defined checks / conditions
                if not config:
                    continue

                self.logger.info("Attempting to selectively poke at %s index", index)
                self._poke_index(config["cmd"], config["checks"])

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
                    config["cmd"], RPM_CHECK_TIMEOUT_SEC, raise_on_nonzero=False
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
            cmd = "{} --dbpath {} -qa".format(self.rpm_path, self.dbpath)
            result = run_with_timeout(cmd, RPM_CHECK_TIMEOUT_SEC)
        except DcRPMException:
            self.logger.error("rpm -qa failed")
            self.status_logger.warning("initial_db_check_fail")
            raise DBNeedsRecovery()

        packages = result.stdout.strip().split()
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
            cmd = "{} --dbpath {} -q {}".format(self.rpm_path, self.dbpath, rpm_name)
            result = run_with_timeout(cmd, RPM_CHECK_TIMEOUT_SEC)
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
        cmd = "{} -h {}".format(self.recover_path, self.dbpath)

        proc = run_with_timeout(cmd, RECOVER_TIMEOUT_SEC, raise_on_nonzero=False)
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
        cmd = "{} --dbpath {} --rebuilddb".format(self.rpm_path, self.dbpath)
        try:
            run_with_timeout(cmd, REBUILD_TIMEOUT_SEC)
        except DcRPMException:
            self.status_logger.warning("rebuild_tables_failed")
            raise

    def check_tables(self):
        # type: () -> None
        """
        Runs the following:

          `rpm -qa --qf | sort | uniq | xargs rpm -q | grep 'is not installed$'`

        which checks each rpm in the DB to see if there are inconsistencies between what
        rpm thinks is installed and what is in the DB.
        """
        cmd = (
            "{rpm} --dbpath {db} -qa --qf '%{NAME}\\n' | sort | uniq | "
            "xargs {rpm} --dbpath {db} -q | grep 'is not installed$'"
        ).format(rpm=self.rpm_path, db=self.dbpath, NAME="NAME")

        try:
            result = run_with_timeout(
                cmd, timeout=RPM_CHECK_TIMEOUT_SEC, raise_on_nonzero=False
            )
        except DcRPMException:
            self.status_logger.warning("initial_table_check_fail")
            raise

        # Grep exit code 1 indicates it didn't find bad condition.
        if result.returncode == 0:
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

            cmd = "{} {}".format(self.verify_path, os.path.join(self.dbpath, table))
            try:
                result = run_with_timeout(
                    cmd, VERIFY_TIMEOUT_SEC, raise_on_nonzero=False
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
        cmd = "{} --cleanup".format(self.yum_complete_transaction_path)
        self.status_logger.info(RepairAction.CLEAN_YUM_TRANSACTIONS)
        run_with_timeout(
            cmd,
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
