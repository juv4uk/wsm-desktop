#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Volnist
"""Write one KDE Plasma phase-2 readiness observation to XDG_RUNTIME_DIR."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGED_SITE = ROOT / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
if (ROOT / "wsm_perf").is_dir():
    sys.path.insert(0, str(ROOT))
elif PACKAGED_SITE.is_dir():
    sys.path.insert(0, str(PACKAGED_SITE))

from wsm_perf.session import (  # noqa: E402
    SCHEMA,
    VERSION,
    SessionReadinessError,
    collect_session_readiness,
    write_session_readiness,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wsm-session-marker",
        description="Record the KDE Plasma autostart phase-2 session milestone.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION} ({SCHEMA})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    try:
        artifact = collect_session_readiness()
        runtime_dir = Path(os.environ["XDG_RUNTIME_DIR"])
        write_session_readiness(artifact, runtime_dir=runtime_dir)
    except (KeyError, OSError, SessionReadinessError) as exc:
        print(f"wsm-session-marker: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
