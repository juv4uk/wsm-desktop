#!/bin/sh
# SPDX-License-Identifier: LicenseRef-Volnist
set -eu
exec python3 -c 'from wsm_install.cli import main; raise SystemExit(main())' "$@"
