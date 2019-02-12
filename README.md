# dcrpm

[![Build Status](https://travis-ci.org/facebookincubator/dcrpm.svg)](http://travis-ci.org/facebookincubator/dcrpm) [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)

dcrpm ("detect and correct rpm") is a tool to detect and correct common issues around RPM database corruption. It attempts a query against your RPM database and runs db4's `db_recover` if it's hung or otherwise seems broken. It then kills any jobs which had the RPM db open previously since they will be stuck in infinite loops within libdb and can't recover cleanly.

## Usage
Run `dcrpm` with no option to detect and correct any outstanding issues with RPM on your host. Additional options can be used to customize logging or select specific remediations. dcrpm is meant to be run from cron regularly to keep things happy and healthy.

## Requirements
dcrpm requires Python 2.7 and above and the package psutil. It also requires `lsof` to be in `$PATH`. It should work on any Linux distribution with RPM and on Mac OS X.

## Building and installing dcrpm
The easiest way to install dcrpm is get the source and install it using setup.py:

    python setup.py install

This will fetch psutil from pypi for you. dcrpm also assumes that the system will have RPM and Yum installed.


## Building and installing for development
If you want to develop, the easiest way to get dcrpm is by using pip:

    pip install -r requirements.txt # get extra packages
    python setup.py install

When developing it's important to make sure the tests continue to pass, and to ensure new features have the appropriate test coverage. You can run the test suite with:

    python setup.py test

which will fetch mock from pypi if needed and then run the tests.

## Contribute
See the CONTRIBUTING file for how to help out.

## License
dcrpm is GPLv2-licensed.
