# SPDX-License-Identifier: LicenseRef-Volnist
"""Render installer steps as data; real APPLY is deliberately disabled.

A command list plus a matching /dev path is not authorization. Before any
privileged writer can return, WSM needs a typed immutable plan, independently
observed device identity, digest-bound consent for every destructive boundary,
a verified Guix tool closure, real postconditions, and disposable-device
acceptance. This module is a preview renderer only.
"""

from __future__ import annotations

import re
import shlex
import sys
from dataclasses import dataclass
from typing import Callable, Sequence

from wsm_install.install_steps import Step
from wsm_install.partition import DEVICE_PATH


class ExecutorError(Exception):
    """A refusal with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class StepResult:
    command: tuple[str, ...]
    purpose: str
    destructive: bool
    status: str
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "command": list(self.command),
            "purpose": self.purpose,
            "destructive": self.destructive,
            "status": self.status,
            "detail": self.detail,
        }


def device_argument_belongs_to_disk(disk: str, operand: str) -> bool:
    """Check preview consistency; this is not a physical-device identity proof."""
    if operand == disk:
        return True
    suffix = r"p[1-9][0-9]*" if disk.startswith(("/dev/nvme", "/dev/mmcblk")) else r"[1-9][0-9]*"
    return re.fullmatch(re.escape(disk) + suffix, operand) is not None


def _validate_preview(disk: str, steps: Sequence[Step]) -> None:
    if not isinstance(disk, str) or DEVICE_PATH.fullmatch(disk) is None:
        raise ExecutorError(
            "execute.disk-path",
            f"{disk!r} is not an allow-listed whole block-device path",
        )
    if isinstance(steps, (str, bytes)) or not isinstance(steps, Sequence):
        raise ExecutorError("execute.steps", "steps must be a sequence of Step values")

    for index, step in enumerate(steps, start=1):
        if not isinstance(step, Step):
            raise ExecutorError("execute.step-type", f"step {index} is not a Step")
        if not isinstance(step.command, (list, tuple)) or not step.command:
            raise ExecutorError(
                "execute.command", f"step {index} must contain a non-empty argv sequence"
            )
        for argument in step.command:
            if (
                not isinstance(argument, str)
                or not argument
                or any(ord(character) < 32 or ord(character) == 127 for character in argument)
            ):
                raise ExecutorError(
                    "execute.command", f"step {index} contains an invalid argv element"
                )
            if argument.startswith("/dev/") and not device_argument_belongs_to_disk(disk, argument):
                raise ExecutorError(
                    "execute.target-mismatch",
                    f"step {index} names {argument!r}, outside preview target {disk!r}",
                )
        if not isinstance(step.purpose, str) or not step.purpose.strip():
            raise ExecutorError("execute.purpose", f"step {index} has no purpose")
        if not isinstance(step.destructive, bool):
            raise ExecutorError("execute.destructive", f"step {index} has an invalid flag")


def execute(
    steps: Sequence[Step],
    disk: str,
    *,
    dry_run: bool = True,
    out: Callable[[str], None] | None = None,
) -> list[StepResult]:
    """Render a preview. Every non-literal-True dry_run request is refused."""
    if dry_run is not True:
        raise ExecutorError(
            "execute.apply-disabled",
            "APPLY is disabled: a preview path and text confirmation do not prove "
            "stable block-device identity or authorize destructive writes",
        )

    _validate_preview(disk, steps)
    emit = out or (lambda line: print(line, file=sys.stderr))
    results: list[StepResult] = []
    emit(f"Preview context only: {disk}; no device identity was probed")
    for index, step in enumerate(steps, start=1):
        command = tuple(step.command)
        result = StepResult(
            command=command,
            purpose=step.purpose,
            destructive=step.destructive,
            status="skipped",
            detail="preview only; APPLY disabled; command not executed",
        )
        results.append(result)
        marker = "DESTRUCTIVE" if step.destructive else "read-only intent"
        emit(
            f"[{index}/{len(steps)}] [{marker}] "
            f"{shlex.join(command)} — {step.purpose}"
        )
    return results
