#!/bin/sh
# SPDX-License-Identifier: LicenseRef-Volnist
set -eu
work_dir=$(mktemp -d "${TMPDIR:-/tmp}/wsm-install-live.XXXXXXXX")
chmod 700 "$work_dir"
cleanup() { rm -rf -- "$work_dir"; }
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
report="$work_dir/hardware-report.json"
wsm-hwcheck --output "$report"
wsm-install --preflight --dry-run --report "$report" --backend guix --tui
