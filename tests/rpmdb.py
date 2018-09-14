#!/usr/bin/env python
#
# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the GPLv2 license found in the LICENSE
# file in the root directory of this source tree.
#

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import shutil
import tarfile
import tempfile


class RPMDB:

    path = ""

    @classmethod
    def _decorator(cls, temp_dir):
        def _inner_decorator(function):
            def wrapper(*args, **kwargs):
                args += (os.path.join(temp_dir, "rpm"),)
                result = function(*args, **kwargs)
                try:
                    # Try cleaning up the temp dir
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
                return result

            return wrapper

        return _inner_decorator

    @classmethod
    def _extract_local_tarfile(cls, filename):
        file = os.path.join(cls.path, "{}.tar.gz".format(filename))
        if os.path.isfile(file) and tarfile.is_tarfile(file):
            try:
                temp_dir = tempfile.mkdtemp()
                tar = tarfile.open(file)
                tar.extractall(temp_dir)
                tar.close()
            except Exception:
                raise Exception("Failed to extract {}".format(file))
        else:
            raise Exception("{} not found or wrong format".format(file))

        return temp_dir

    @classmethod
    def from_file(cls, filename):
        return cls._decorator(cls._extract_local_tarfile(filename))
