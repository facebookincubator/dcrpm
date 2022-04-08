# dcrpm

[![Continuous Integration](https://github.com/facebookincubator/dcrpm/actions/workflows/ci.yml/badge.svg)](https://github.com/facebookincubator/dcrpm/actions/workflows/ci.yml) [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

dcrpm ("detect and correct rpm") is a tool to detect and correct common issues around RPM database corruption. It attempts a query against your RPM database and runs db4's `db_recover` if it's hung or otherwise seems broken. It then kills any jobs which had the RPM db open previously since they will be stuck in infinite loops within libdb and can't recover cleanly.

## Usage
Run `dcrpm` with no option to detect and correct any outstanding issues with RPM on your host. Additional options can be used to customize logging or select specific remediations. dcrpm is meant to be run from cron regularly to keep things happy and healthy.

## Requirements
dcrpm requires Python 2.7 and above and the package psutil. It also requires `lsof` to be in `$PATH`. It should work on any Linux distribution with RPM and on Mac OS X.

To use `setup.py` you need setuptools >= 40.9.0 (see [setup.cfg-only projects](https://setuptools.pypa.io/en/latest/setuptools.html#setup-cfg-only-projects)).
Substitute `legacy_setup.py` if you have an older setuptools (e.g. when building on EL 8).

## Installing dcrpm
dcrpm is packaged in Fedora as of Fedora 32 and in EPEL as of EPEL 8. It can be installed with:

    dnf install dcrpm

This will also install any necessary dependencies at the same time.

## Building and installing dcrpm from source
The easiest way to manually install dcrpm is get the source and install it using setup.py:

    python setup.py install

This will fetch psutil from PyPI for you. dcrpm also assumes that the system will have RPM and Yum or DNF installed.


## Building and installing for development
If you want to develop, the easiest way to get dcrpm is by using pip:

    pip install -r requirements-test.txt # get extra packages
    python setup.py install

When developing it's important to make sure the tests continue to pass, and to ensure new features have the appropriate test coverage. You can run the test suite with:

    pytest


## Preparing a new release
First, install some extra packages:

    pip install -r requirements-release.txt

Then create the source distribution and the wheel:

### Old style

    python setup.py sdist bdist_wheel --universal

### With the build module

This has the advantage of performing the build in an isolated virtual environment. However, it does not build a universal (py2/py3) wheel anymore.

    python -m build

Then verify them:

    twine check dist/*

A `Makefile` is provided to simplify this

    make dist
    make dist USE_BUILD=1  # use the build module, soon to be default
    make dist USE_LEGACY=1 # use legacy_setup.py
    make check-release

## Contribute
See the CONTRIBUTING file for how to help out.

## License
dcrpm is GPLv2-licensed.
