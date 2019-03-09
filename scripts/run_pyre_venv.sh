#!/usr/bin/env bash

set -eu
set -o pipefail

[[ -z "${VIRTUAL_ENV}" ]] && echo "not in a virtualenv, exiting" && exit 1

function get_site_packages() {
    python - <<EOF
from __future__ import print_function
from distutils.sysconfig import get_python_lib
print(get_python_lib())
EOF
}

root=$(git rev-parse --show-toplevel)

"${VIRTUAL_ENV}/bin/pyre" \
    --source-directory "$root/dcrpm" \
    --source-directory "$root/tests" \
    --typeshed "${VIRTUAL_ENV}/lib/pyre_check/typeshed" \
    --output text \
    --search-path "$(get_site_packages)" \
    --search-path "$root" \
    check
