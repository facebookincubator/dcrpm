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

import argparse
import json
import logging
import logging.config
import sys

from . import __version__
from .dcrpm import DcRPM
from .rpmutil import RPMUtil
from .util import which

# Some sensible defaults.
DEFAULT_MAX_PASSES = 5

# Taken from the original C++ dcrpm
DEFAULT_MIN_REQUIRED_FREE_SPACE = 150 * 1048576

LOG_FORMAT = "%(asctime)s %(levelname)s [%(module)s.%(funcName)s]: %(message)s"
DEFAULT_LOGGING_CONFIG = {
    "version": 1,
    "formatters": {"standard": {"format": LOG_FORMAT}},
    "handlers": {
        "console": {
            "level": "INFO",
            "formatter": "standard",
            "class": "logging.StreamHandler",
        },
        "file": {
            "level": "DEBUG",
            "formatter": "standard",
            "class": "logging.FileHandler",
            "filename": "/var/log/dcrpm.log",
        },
        "forensic_logger": {
            "level": "DEBUG",
            "formatter": "standard",
            "class": "dcrpm.forensic_logger.ForensicLogger",
            "logdir": "/tmp",
        },
    },
    "loggers": {
        "": {"handlers": ["console", "file"]},
        "status": {"handlers": ["console", "forensic_logger"]},
    },
}


def parse_args():
    parser = argparse.ArgumentParser(
        prog="dcrpm", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s " + __version__
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode, do not execute any operations",
    )
    parser.add_argument(
        "--check-stuck-yum",
        action="store_true",
        help="Run stuck yum check and remediation",
    )
    parser.add_argument(
        "--rpm-path", metavar="PATH", default=which("rpm"), help="Path to rpm"
    )
    parser.add_argument(
        "--recover-path",
        metavar="PATH",
        default=which("db_recover"),
        help="Path to db_recover",
    )
    parser.add_argument(
        "--verify-path",
        metavar="PATH",
        default=which("db_verify"),
        help="Path to db_verify",
    )
    parser.add_argument(
        "--stat-path", metavar="PATH", default=which("db_stat"), help="Path to db_stat"
    )
    parser.add_argument(
        "--clean-yum-transactions",
        action="store_true",
        help="Clean stale yum transactions using yum-complete-transaction",
    )
    parser.add_argument(
        "--run-yum-clean", action="store_true", help="Check for yum clean failures"
    )
    parser.add_argument(
        "--run-yum-check",
        action="store_true",
        help='Use "yum check" to find rpmdb problems',
    )
    parser.add_argument(
        "--yum-complete-transaction-path",
        metavar="PATH",
        default="/usr/sbin/yum-complete-transaction",
        help="Path to yum-complete-transaction",
    )
    parser.add_argument(
        "--dbpath", metavar="PATH", default="/var/lib/rpm", help="Path to RPM database"
    )
    parser.add_argument(
        "--max-passes",
        type=int,
        metavar="N",
        default=DEFAULT_MAX_PASSES,
        help="Run N passes of checks/remediations",
    )
    parser.add_argument(
        "--minspace",
        type=int,
        metavar="BYTES",
        default=DEFAULT_MIN_REQUIRED_FREE_SPACE,
        help="Minimum free space in bytes required",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Log debug messages"
    )
    parser.add_argument(
        "-f",
        "--forensic",
        action="store_true",
        help="Collect debug output for forensic investigations",
    )
    parser.add_argument(
        "-l",
        "--logging-config-file",
        metavar="FILE",
        help="JSON file containing python logger configuration",
    )
    parser.add_argument(
        "--blacklist",
        nargs="+",
        default=["Filedigests", "Obsoletename", "Provideversion"],
        help="Databases to blacklist from db_verify",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Set up logging
    if args.logging_config_file:
        with open(args.logging_config_file) as f:
            logging.config.dictConfig(json.load(f))
    else:
        logging.config.dictConfig(DEFAULT_LOGGING_CONFIG)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Let's go!
    rpmutil = RPMUtil(
        dbpath=args.dbpath,
        rpm_path=args.rpm_path,
        recover_path=args.recover_path,
        verify_path=args.verify_path,
        stat_path=args.stat_path,
        yum_complete_transaction_path=args.yum_complete_transaction_path,
        blacklist=args.blacklist,
        forensic=args.forensic,
    )
    try:
        rc = DcRPM(rpmutil, args).run()
        return int(not (rc))
    except Exception as e:
        msg = "exception: {}".format(e)
        logging.getLogger("status").error("exception")
        logging.getLogger().error(msg)


if __name__ == "__main__":
    sys.exit(main())
