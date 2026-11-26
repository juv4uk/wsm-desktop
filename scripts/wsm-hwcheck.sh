#!/bin/sh
# SPDX-License-Identifier: LicenseRef-Volnist
set -eu
exec python3 -m wsm_hwcheck "$@"
