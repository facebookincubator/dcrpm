#!/bin/sh
#
# Copyright (c) 2019-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the GPLv2 license found in the LICENSE
# file in the root directory of this source tree.

set -e

[ -z "${VIRTUAL_ENV}" ] && echo "not in a virtualenv, exiting" && exit 1

set -u

get_site_packages() {
    python - <<EOF
from __future__ import print_function
from distutils.sysconfig import get_python_lib
print(get_python_lib())
EOF
}

root=$(git rev-parse --show-toplevel)

"${VIRTUAL_ENV}/bin/pyre" \
    --noninteractive \
    --source-directory "$root/dcrpm" \
    --source-directory "$root/tests" \
    --typeshed "${VIRTUAL_ENV}/lib/pyre_check/typeshed" \
    --output text \
    --search-path "$(get_site_packages)" \
    --search-path "$root" \
    --show-parse-errors \
    check
