# SPDX-License-Identifier: LicenseRef-Volnist
"""Privileged plan reader, currently restricted to validation and preview.

A plan written by the unprivileged UI is untrusted input, not permission to
mutate a disk. The worker remains preview-only until an immutable plan is bound
to independently observed block-device identity and digest-bound consent.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Sequence

from wsm_install.executor import (
    ExecutorError,
    device_argument_belongs_to_disk,
    execute,
)
from wsm_install.install_steps import Step
from wsm_install.partition import DEVICE_PATH

# Absolute executable names remain a structural restriction for preview data.
# Their presence here is not evidence that they exist in the locked Guix image.
ALLOWED_PROGRAMS = frozenset({
    "/usr/sbin/partprobe",
    "/usr/bin/udevadm",
    "/usr/sbin/mkfs.ext4",
    "/usr/sbin/mkfs.btrfs",
    "/usr/sbin/mkfs.xfs",
    "/usr/sbin/mkfs.fat",
    "/usr/bin/mount",
    "/usr/bin/mkdir",
})

SHELL_METACHARACTERS = frozenset("|&;<>()$`\\\"'\n\r")
MAX_STEPS = 32
MAX_PLAN_BYTES = 1024 * 1024


class AgentError(Exception):
    """A refusal with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def validate_command(command: Sequence[str]) -> None:
    if not isinstance(command, (list, tuple)) or not command:
        raise AgentError("agent.empty-command", "a step has no command argv")
    program = command[0]
    if not isinstance(program, str) or program not in ALLOWED_PROGRAMS:
        raise AgentError(
            "agent.not-allowed",
            f"{program!r} is not in the agent allowlist; commands are preview data only",
        )
    for argument in command:
        if (
            not isinstance(argument, str)
            or not argument
            or any(ord(character) < 32 or ord(character) == 127 for character in argument)
        ):
            raise AgentError("agent.bad-argument", f"invalid argv element: {argument!r}")
        if SHELL_METACHARACTERS & set(argument):
            raise AgentError(
                "agent.shell-metacharacter",
                f"argument {argument!r} contains a shell metacharacter",
            )


def validate_plan(document: Any) -> list[Step]:
    """Turn an untrusted plan document into preview steps."""
    if not isinstance(document, dict):
        raise AgentError("agent.bad-plan", "the plan must be a JSON object")
    if document.get("schema") != "wsm-install-plan/1":
        raise AgentError(
            "agent.bad-schema",
            f"expected schema 'wsm-install-plan/1', got {document.get('schema')!r}",
        )

    disk = document.get("disk")
    if not isinstance(disk, str) or DEVICE_PATH.fullmatch(disk) is None:
        raise AgentError("agent.bad-disk", f"the plan must name a whole block device: {disk!r}")

    raw_steps = document.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise AgentError("agent.no-steps", "the plan contains no steps")
    if len(raw_steps) > MAX_STEPS:
        raise AgentError(
            "agent.too-many-steps",
            f"{len(raw_steps)} steps exceeds the limit of {MAX_STEPS}",
        )

    steps: list[Step] = []
    for index, entry in enumerate(raw_steps, start=1):
        if not isinstance(entry, dict):
            raise AgentError("agent.bad-step", f"step {index} is not an object")
        command = entry.get("command")
        validate_command(command if isinstance(command, (list, tuple)) else [])
        for argument in command:
            if argument.startswith("/dev/") and not device_argument_belongs_to_disk(disk, argument):
                raise AgentError(
                    "agent.target-mismatch",
                    f"step {index} targets {argument!r}, not the declared preview target {disk!r}",
                )

        purpose = entry.get("purpose")
        destructive = entry.get("destructive")
        if not isinstance(purpose, str) or not purpose.strip():
            raise AgentError("agent.bad-purpose", f"step {index} has no valid purpose")
        if not isinstance(destructive, bool):
            raise AgentError("agent.bad-step", f"step {index} has a non-boolean destructive flag")
        steps.append(Step(command=list(command), purpose=purpose, destructive=destructive))
    return steps


def load_plan(path: Path) -> tuple[dict[str, Any], list[Step]]:
    """Read only a bounded regular file, refusing symlink and special-file inputs."""
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise AgentError("agent.unsafe-plan-path", "plan path must be a regular, non-symlink file")
        if metadata.st_size > MAX_PLAN_BYTES:
            raise AgentError("agent.plan-too-large", f"plan exceeds {MAX_PLAN_BYTES} bytes")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_PLAN_BYTES:
                raise AgentError("agent.unsafe-plan-path", "opened plan is not a bounded regular file")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                raw = stream.read(MAX_PLAN_BYTES + 1)
        finally:
            os.close(descriptor)
        if len(raw) > MAX_PLAN_BYTES:
            raise AgentError("agent.plan-too-large", f"plan exceeds {MAX_PLAN_BYTES} bytes")
        document = json.loads(raw.decode("utf-8"))
    except AgentError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AgentError("agent.unreadable-plan", f"cannot read {path}: {exc}") from exc
    return document, validate_plan(document)


def run_plan(document: dict[str, Any], steps: list[Step], dry_run: bool) -> int:
    """Accept preview only. No privilege level can enable real execution."""
    if dry_run is not True:
        raise AgentError(
            "agent.apply-disabled",
            "real APPLY is disabled until target identity, digest-bound consent, "
            "verified tools and device postconditions are implemented",
        )

    validated = validate_plan(document)
    if steps != validated:
        raise AgentError("agent.plan-mismatch", "supplied steps differ from the validated plan")
    disk = document["disk"]

    try:
        execute(validated, disk=disk, dry_run=True)
    except ExecutorError as exc:
        raise AgentError("agent.preview-failed", f"{exc.code}: {exc.message}") from exc
    return 0


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="wsm-install-agent",
        description=(
            "Privileged plan validator. This version only validates and previews; "
            "it never writes to disks."
        ),
    )
    parser.add_argument("--plan", type=Path, help="install plan JSON (or journal with --recover)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="validate and preview only (the only supported mode)",
    )
    parser.add_argument(
        "--recover",
        action="store_true",
        help="describe the state a failed install left behind, from the journal",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.recover:
        from wsm_install.journal import recovery_report

        if args.plan is None:
            print("wsm-install-agent: --plan is required with --recover", file=sys.stderr)
            return 2
        sys.stdout.write(recovery_report(args.plan))
        return 0
    if args.plan is None:
        print("wsm-install-agent: --plan is required", file=sys.stderr)
        return 2

    try:
        document, steps = load_plan(args.plan)
        run_plan(document, steps, args.dry_run)
    except AgentError as exc:
        print(f"wsm-install-agent: {exc.code}: {exc.message}", file=sys.stderr)
        return 1
    print(
        f"wsm-install-agent: preview accepted ({len(steps)} step(s)); no disk was changed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
