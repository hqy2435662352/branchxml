#!/bin/sh
set -eu
appdir=$(CDPATH= cd -- "$(dirname -- "$(readlink -f -- "$0")")/../share/branchxml" && pwd)
exec @PYTHON@ "$appdir/branchxml.py" "$@"
