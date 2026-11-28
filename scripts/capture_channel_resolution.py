#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Volnist
"""Capture an auditable, machine-checkable Guix channel-resolution transcript."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

SCHEMA = "wsm-channel-resolution/1"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture(command: Sequence[str]) -> tuple[bytes, bytes, int, str | None]:
    """Run the exact locked describe command without a shell."""
    try:
        result = subprocess.run(list(command), capture_output=True, check=False)
    except OSError as exc:
        message = f"{type(exc).__name__}: {exc}"
        return b"", message.encode("utf-8", errors="replace"), 127, message
    return result.stdout, result.stderr, result.returncode, None


def evidence_document(
    command: Sequence[str],
    stdout: bytes,
    stderr: bytes,
    exit_status: int,
    launch_error: str | None = None,
) -> dict[str, object]:
    """Build a complete transcript, including an explicit empty-stderr record."""
    document: dict[str, object] = {
        "schema": SCHEMA,
        "command": list(command),
        "exit_status": exit_status,
        "stdout": {
            "file": "channels.resolved.scm",
            "bytes": len(stdout),
            "sha256": sha256(stdout),
        },
        "stderr": {
            "bytes": len(stderr),
            "sha256": sha256(stderr),
            "base64": base64.b64encode(stderr).decode("ascii"),
            "text": stderr.decode("utf-8", errors="replace"),
        },
    }
    if launch_error is not None:
        document["launch_error"] = launch_error
    return document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capture-channel-resolution",
        description="Capture Guix locked channel resolution and its complete evidence.",
    )
    parser.add_argument("--guix", required=True, help="absolute path to the Guix executable")
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--channels-output", required=True, type=Path)
    parser.add_argument("--log-output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = [
        str(Path(args.guix).resolve()),
        "time-machine",
        "-C",
        str(args.lock.resolve()),
        "-L",
        str(args.repo_root.resolve()),
        "--",
        "describe",
        "-f",
        "channels",
    ]
    stdout, stderr, status, launch_error = capture(command)
    args.channels_output.write_bytes(stdout)
    document = evidence_document(command, stdout, stderr, status, launch_error)
    args.log_output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if launch_error is not None:
        print(f"channel-resolution: could not start Guix: {launch_error}", file=sys.stderr)
        return 127
    if status != 0:
        print(f"channel-resolution: Guix exited with status {status}", file=sys.stderr)
        if stderr:
            sys.stderr.write(stderr.decode("utf-8", errors="replace"))
        return status if 1 <= status <= 125 else 1
    if not stdout:
        print("channel-resolution: Guix succeeded but returned an empty channel description", file=sys.stderr)
        return 1
    combined = (stdout + b"\n" + stderr).lower()
    if b"channel authentication disabled" in combined:
        print("channel-resolution: refusing disabled channel authentication", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
