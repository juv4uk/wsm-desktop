# SPDX-License-Identifier: LicenseRef-Volnist
"""Render installer steps as a dry-run; real disk execution is intentionally disabled.

The previous executor accepted arbitrary Step objects and an acknowledgement
string that was not bound to the devices in those commands. Until a typed,
target-bound authorization and verified runtime toolchain exist, this module
must not execute destructive commands.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable, Sequence

from wsm_install.install_steps import Step


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

    def as_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "purpose": self.purpose,
            "destructive": self.destructive,
            "status": self.status,
            "detail": self.detail,
        }


def execute(
    steps: Sequence[Step],
    disk: str,
    *,
    dry_run: bool = True,
    out: Callable[[str], None] | None = None,
) -> list[StepResult]:
    """Return a dry-run preview; refuse every real execution request.

    Step remains a data object and is not sufficient authority to write a
    disk. Real execution will require a validated immutable plan bound to the
    exact target's runtime identity, a trusted executable allowlist, and a
    per-destructive-step confirmation/revalidation contract.
    """
    if dry_run is not True:
        raise ExecutorError(
            "execute.real-mode-disabled",
            "real disk execution is disabled until target binding, runtime identity "
            "revalidation, trusted verifier tools, and per-step authorization are implemented",
        )

    emit = out or (lambda line: print(line, file=sys.stderr))
    results: list[StepResult] = []
    emit(f"dry-run target: {disk}")
    for index, step in enumerate(steps, start=1):
        result = StepResult(
            command=list(step.command),
            purpose=step.purpose,
            destructive=step.destructive,
            status="skipped",
            detail="dry run; no command was executed",
        )
        results.append(result)
        printable = " ".join(step.command)
        marker = "DESTRUCTIVE" if step.destructive else "read-only"
        emit(f"[{index}/{len(steps)}] [{marker}] would run: {printable}")
    return results
