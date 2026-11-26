# SPDX-License-Identifier: LicenseRef-Volnist
"""A privileged worker that validates plans but never mutates disks.

The allowlist and argument checks remain useful defense in depth, but they do
not prove stable block-device identity or bind authorization to an immutable
plan. Until those properties exist, this module is preview-only. A plan passed
without the explicit --dry-run flag is refused before the executor is called.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Sequence

from wsm_install.executor import ExecutorError, execute
from wsm_install.install_steps import Step

# Everything the agent is allowed to run. Absolute paths only: a bare name would
# be resolved through PATH, which is the Omarchy #8172 mistake.
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


class AgentError(Exception):
    """A refusal with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def validate_command(command: Sequence[str]) -> None:
    if not command:
        raise AgentError("agent.empty-command", "a step has no command")
    program = command[0]
    if program not in ALLOWED_PROGRAMS:
        raise AgentError(
            "agent.not-allowed",
            f"{program!r} is not in the agent allowlist; the agent runs only what "
            "the installer needs and nothing else",
        )
    for argument in command[1:]:
        if not isinstance(argument, str):
            raise AgentError("agent.bad-argument", f"non-string argument: {argument!r}")
        if SHELL_METACHARACTERS & set(argument):
            raise AgentError(
                "agent.shell-metacharacter",
                f"argument {argument!r} contains a shell metacharacter; the agent "
                "never lets a shell near a disk",
            )


def validate_plan(document: Any) -> list[Step]:
    """Turn a plan document into steps, refusing anything unexpected."""
    if not isinstance(document, dict):
        raise AgentError("agent.bad-plan", "the plan must be a JSON object")
    if document.get("schema") != "wsm-install-plan/1":
        raise AgentError(
            "agent.bad-schema",
            f"expected schema 'wsm-install-plan/1', got {document.get('schema')!r}",
        )
    raw_steps = document.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise AgentError("agent.no-steps", "the plan contains no steps")
    if len(raw_steps) > MAX_STEPS:
        raise AgentError(
            "agent.too-many-steps",
            f"{len(raw_steps)} steps exceeds the limit of {MAX_STEPS}",
        )

    steps: list[Step] = []
    for entry in raw_steps:
        if not isinstance(entry, dict):
            raise AgentError("agent.bad-step", f"a step is not an object: {entry!r}")
        command = entry.get("command")
        if not isinstance(command, list):
            raise AgentError("agent.bad-step", f"a step has no command list: {entry!r}")
        validate_command(command)
        steps.append(Step(
            command=list(command),
            purpose=str(entry.get("purpose", "")),
            destructive=bool(entry.get("destructive", False)),
        ))
    return steps


def load_plan(path: Path) -> tuple[dict[str, Any], list[Step]]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentError("agent.unreadable-plan", f"cannot read {path}: {exc}") from exc
    return document, validate_plan(document)


def run_plan(
    document: dict[str, Any],
    steps: list[Step],
    dry_run: bool,
) -> int:
    """Render a preview; fail closed for every request to mutate a disk."""
    disk = document.get("disk")
    if not isinstance(disk, str) or not disk.startswith("/dev/"):
        raise AgentError("agent.bad-disk", f"the plan names no block device: {disk!r}")

    if dry_run is not True:
        raise AgentError(
            "agent.apply-disabled",
            "real disk mutation is disabled: the plan is not bound to a stable "
            "device identity and digest-bound authorization",
        )

    try:
        execute(steps, disk=disk, dry_run=True)
    except ExecutorError as exc:
        raise AgentError("agent.execution-failed", f"{exc.code}: {exc.message}") from exc
    return 0

def build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="wsm-install-agent",
        description=(
            "Privileged worker: validate an install plan against an allowlist and render "
            "a preview only. Real disk mutation is disabled until target-bound authorization "
            "is implemented."
        ),
    )
    parser.add_argument("--plan", type=Path, help="install plan JSON (or the journal with --recover)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and render a preview only; real disk mutation is disabled",
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
        if args.plan is None:
            print(
                "wsm-install-agent: --plan is required with --recover",
                file=sys.stderr,
            )
            return 2
        from wsm_install.journal import recovery_report

        sys.stdout.write(recovery_report(Path(args.plan)))
        return 0
    if args.plan is None:
        print("wsm-install-agent: --plan is required unless --recover is given", file=sys.stderr)
        return 2

    try:
        document, steps = load_plan(args.plan)
        run_plan(document, steps, args.dry_run)
    except AgentError as exc:
        print(f"wsm-install-agent: {exc.code}: {exc.message}", file=sys.stderr)
        return 1
    print(
        f"wsm-install-agent: preview generated ({len(steps)} step(s)); "
        "no disk commands were executed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
