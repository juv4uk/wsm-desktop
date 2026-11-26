# SPDX-License-Identifier: LicenseRef-Volnist
"""Read-only privileged plan validator; real disk APPLY is deliberately disabled.

The split between an unprivileged UI and a privileged worker is a useful
architecture boundary, but an allowlist alone does not authorize formatting a
disk. Plans are not signed or bound to a stable block-device identity, and the
tool paths have not been proven present in the pinned Guix system closure.

For now this agent validates and previews plans only. Any request other than
the literal dry-run mode fails before it can invoke an external command.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Sequence

from wsm_install.executor import ExecutorError, execute
from wsm_install.install_steps import Step, TRUSTED_TOOLS
from wsm_install.partition import DEVICE_PATH

# Keep one source of truth with the planner; this is not proof that each path
# exists in the eventual Guix closure. Future APPLY needs a separate closure gate.
ALLOWED_PROGRAMS = frozenset(
    value for value in TRUSTED_TOOLS.values() if isinstance(value, str)
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
    if not isinstance(command, (list, tuple)) or not command:
        raise AgentError("agent.empty-command", "a step has no command")
    program = command[0]
    if not isinstance(program, str) or program not in ALLOWED_PROGRAMS:
        raise AgentError(
            "agent.not-allowed",
            f"{program!r} is not in the planner's trusted tool table",
        )
    for argument in command[1:]:
        if not isinstance(argument, str):
            raise AgentError("agent.bad-argument", f"non-string argument: {argument!r}")
        if SHELL_METACHARACTERS & set(argument):
            raise AgentError(
                "agent.shell-metacharacter",
                f"argument {argument!r} contains a shell metacharacter",
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
        purpose = entry.get("purpose", "")
        destructive = entry.get("destructive", False)
        if not isinstance(purpose, str) or not isinstance(destructive, bool):
            raise AgentError("agent.bad-step", "purpose must be text and destructive must be boolean")
        steps.append(Step(
            command=list(command),
            purpose=purpose,
            destructive=destructive,
        ))
    return steps


def load_plan(path: Path) -> tuple[dict[str, Any], list[Step]]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AgentError("agent.unreadable-plan", f"cannot read {path}: {exc}") from exc
    return document, validate_plan(document)


def run_plan(
    document: dict[str, Any],
    steps: list[Step],
    dry_run: bool,
) -> int:
    """Preview a validated plan; never execute it."""
    if dry_run is not True:
        raise AgentError(
            "agent.apply-disabled",
            "the privileged worker is preview-only until target binding, "
            "digest-bound consent, verified tool closure and postconditions exist",
        )

    disk = document.get("disk")
    if not isinstance(disk, str) or not DEVICE_PATH.fullmatch(disk):
        raise AgentError("agent.bad-disk", f"the plan names no whole block device: {disk!r}")

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
            "Read-only privileged worker: validate an install plan against the "
            "planner's trusted tool table and render a preview. Real APPLY is disabled."
        ),
    )
    parser.add_argument("--plan", required=True, type=Path, help="install plan JSON")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="required: validate and report only; real APPLY is disabled",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        document, steps = load_plan(args.plan)
        run_plan(document, steps, args.dry_run)
    except AgentError as exc:
        print(f"wsm-install-agent: {exc.code}: {exc.message}", file=sys.stderr)
        return 1
    print(f"wsm-install-agent: preview generated ({len(steps)} step(s)); no disk commands executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
