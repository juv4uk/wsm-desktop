# SPDX-License-Identifier: LicenseRef-Volnist
"""Preview installer steps; refuse every real APPLY until target binding exists.

The previous implementation accepted an arbitrary command list plus a separate
acknowledgement string. That did not prove that the commands targeted the
acknowledged block device, that the device was unchanged since planning, or
that every destructive boundary was revalidated. Its partition-table verifier
was also incomplete and one privileged lookup used PATH.

This module is therefore deliberately preview-only. The function name is kept
for API continuity, but dry_run=False is always refused. Do not add an
"allow apply" flag here. Re-enable disk mutation only in a separate change
that consumes an immutable typed plan and proves target identity, consent,
tool closure, and read-only postconditions in disposable QEMU.
"""

from __future__ import annotations

import re
import shlex
import sys
from dataclasses import dataclass
from typing import Callable, Sequence

from wsm_install.install_steps import TRUSTED_TOOLS, Step
from wsm_install.partition import DEVICE_PATH


class ExecutorError(Exception):
    """A refusal with a stable code, like the rest of the installer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class StepResult:
    command: list[str]
    purpose: str
    destructive: bool
    status: str
    detail: str = ""
    # Whether this command could ever be applied. The preview still renders an
    # inadmissible command so the operator can see what was proposed, but it is
    # never silently treated as safe: the plan does not get to vouch for itself.
    admissible: bool = True
    inadmissible_reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "purpose": self.purpose,
            "destructive": self.destructive,
            "status": self.status,
            "detail": self.detail,
            "admissible": self.admissible,
            "inadmissible_reason": self.inadmissible_reason,
        }


def _is_target_device_path(disk: str, candidate: str) -> bool:
    """Accept only the whole target disk or one of its kernel-style partitions."""
    if candidate == disk:
        return True
    separator = "p" if disk[-1].isdigit() else ""
    prefix = f"{disk}{separator}"
    return re.fullmatch(re.escape(prefix) + r"[1-9][0-9]*", candidate) is not None


def _validate_preview(disk: str, steps: Sequence[Step]) -> None:
    if not isinstance(disk, str) or not DEVICE_PATH.fullmatch(disk):
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
                "execute.command",
                f"step {index} must contain a non-empty argv sequence",
            )
        if any(
            not isinstance(argument, str)
            or not argument
            or any(ord(character) < 32 or ord(character) == 127 for character in argument)
            for argument in step.command
        ):
            raise ExecutorError(
                "execute.command",
                f"step {index} contains an invalid argv element",
            )
        if not isinstance(step.purpose, str) or not step.purpose.strip():
            raise ExecutorError("execute.purpose", f"step {index} has no purpose")
        if not isinstance(step.destructive, bool):
            raise ExecutorError("execute.destructive", f"step {index} has an invalid flag")

        # Check every explicit block-device reference, including references
        # embedded in an option such as "--device=/dev/sda1". A preview for one
        # disk must never display a command that would touch another disk.
        for argument in step.command:
            for referenced in re.findall(r"/dev/[A-Za-z0-9._/-]+", argument):
                if not _is_target_device_path(disk, referenced):
                    raise ExecutorError(
                        "execute.device-mismatch",
                        f"step {index} references {referenced!r}, outside target {disk!r}",
                    )


ALLOWED_EXECUTABLES = frozenset(TRUSTED_TOOLS.values())


def admissible_executable(step: Step) -> tuple[bool, str]:
    """Whether this step's argv[0] may ever reach a runner.

    #280 criterion 2: the executor checks the plan itself instead of trusting the
    planner. A bare name means a PATH lookup, which is the hijack class Omarchy
    #8172 documents; an absolute path outside the pinned tool table means a tool
    that no closure proof covers.
    """
    executable = step.command[0] if step.command else ""
    if not executable.startswith("/"):
        return False, f"{executable!r} is not an absolute path; a PATH lookup is not allowed"
    if executable not in ALLOWED_EXECUTABLES:
        return False, f"{executable!r} is not in the pinned tool allowlist"
    return True, ""


def execute(
    steps: Sequence[Step],
    disk: str,
    *,
    dry_run: bool = True,
    out: Callable[[str], None] | None = None,
) -> list[StepResult]:
    """Render a preview only. Real disk mutation is intentionally disabled."""
    if dry_run is not True:
        raise ExecutorError(
            "execute.apply-disabled",
            "APPLY is disabled: this preview does not bind commands to a stable "
            "device identity or a digest-bound immutable plan",
        )

    _validate_preview(disk, steps)
    emit = out or (lambda line: print(line, file=sys.stderr))
    results: list[StepResult] = []

    for index, step in enumerate(steps, start=1):
        command = list(step.command)
        admissible, reason = admissible_executable(step)
        result = StepResult(
            command=command,
            purpose=step.purpose,
            destructive=step.destructive,
            status="not-run",
            detail="preview only; APPLY disabled; command not executed",
            admissible=admissible,
            inadmissible_reason=reason,
        )
        results.append(result)
        marker = "DESTRUCTIVE" if step.destructive else "read-only intent"
        if not admissible:
            marker = f"{marker}, NOT APPLICABLE"
        emit(
            f"[{index}/{len(steps)}] [{marker}] "
            f"{shlex.join(command)} — {step.purpose}"
        )
        if not admissible:
            emit(f"    refused for APPLY: {reason}")

    return results
