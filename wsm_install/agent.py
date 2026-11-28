# SPDX-License-Identifier: LicenseRef-Volnist
"""A privileged worker that validates and previews installer plans only.

The initial design used this module as a privileged command runner. That
execution path is intentionally disabled: a command allowlist is not proof
that a plan is bound to the intended physical disk, nor that the disk remains
unchanged at each destructive boundary.

The current worker validates plan shape and known command forms, then delegates
to the shared preview-only executor. It never launches a process, writes a
partition table, formats a filesystem, mounts a target, or deploys Guix.

Do not restore APPLY here as a local flag. Any future disk mutation must be
designed and reviewed as one target-bound flow across every frontend, with an
immutable plan, digest-bound consent, repeated device identity checks,
postconditions, recovery evidence, and disposable-QEMU acceptance.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Sequence

from wsm_install.executor import ExecutorError, execute
from wsm_install.install_steps import Step, TRUSTED_PROFILE_ROOT, TRUSTED_TOOLS
from wsm_install.partition import DEVICE_PATH

# Commands recognized by the plan validator. This list is not an execution
# permission while APPLY remains disabled. Absolute paths avoid PATH ambiguity.
# The planner emits exact Guix system-profile paths. Accept both profile
# directories because a package may expose an administrative tool in either;
# the planner separately proves that exactly one candidate is executable.
# FHS paths and bare basenames are deliberately not accepted here.
ALLOWED_PROGRAMS = frozenset(
    str(TRUSTED_PROFILE_ROOT / directory / binary)
    for directory in ("bin", "sbin")
    for binary in TRUSTED_TOOLS.values()
)

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
            f"{program!r} is not in the agent allowlist; this plan contains an "
            "unrecognized command form",
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
    """Validate and preview a plan; never execute a disk mutation."""
    disk = document.get("disk")
    if not isinstance(disk, str) or not DEVICE_PATH.fullmatch(disk):
        raise AgentError("agent.bad-disk", f"the plan names no whole block device: {disk!r}")

    if dry_run is not True:
        raise AgentError(
            "agent.apply-disabled",
            "real disk execution is disabled across all installer entry points; "
            "this agent can validate and preview plans only",
        )

    try:
        execute(steps, disk=disk, dry_run=True)
    except ExecutorError as exc:
        raise AgentError("agent.preview-failed", f"{exc.code}: {exc.message}") from exc
    return 0


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="wsm-install-agent",
        description=(
            "Validate an install plan against the command allowlist and show a preview. "
            "Real disk APPLY is disabled; no command is executed."
        ),
    )
    parser.add_argument("--plan", type=Path, help="install plan JSON (or the journal with --recover)")
    parser.add_argument("--dry-run", action="store_true", help="required; validate and report only")
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
    if not args.dry_run:
        print("wsm-install-agent: agent.apply-disabled: only --dry-run is supported", file=sys.stderr)
        return 2
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
        f"wsm-install-agent: previewed {len(steps)} step(s); "
        "APPLY disabled; no disk command executed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
