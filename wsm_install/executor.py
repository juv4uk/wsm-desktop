# SPDX-License-Identifier: LicenseRef-Volnist
"""Build a dry-run report for an install sequence; real apply is disabled.

This module previously exposed a callable path to run arbitrary Step.command
arrays. That was not a safe execution contract: disk identity was not
revalidated before each destructive action, the acknowledgement was checked
only once, GPT writes had no verifier, and several verifiers reported success
without proving the requested state.

Until a typed plan is bound to a live block-device identity and every
mutating operation has a meaningful verifier and per-step confirmation, this
module is deliberately dry-run only. Passing dry_run=False always fails
closed before the runner or verifier is called.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from wsm_install.install_steps import Step

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]
Verifier = Callable[[Step], tuple[bool, str]]


class ExecutorError(Exception):
    """A refusal with a stable code, like the rest of the installer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class StepResult:
    command: list[str]
    purpose: str
    destructive: bool
    status: str  # planned | done | failed | skipped | unverified
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "purpose": self.purpose,
            "destructive": self.destructive,
            "status": self.status,
            "detail": self.detail,
        }


def default_runner(command: Sequence[str]) -> subprocess.CompletedProcess:
    """Run a step. No shell, ever: the command is already a list."""
    return subprocess.run(list(command), capture_output=True, text=True, check=False)


def read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def default_verifier(step: Step) -> tuple[bool, str]:
    """Check what the step claims to have done, using the filesystem, not exit codes."""
    tool = step.command[0].rsplit("/", 1)[-1]

    if tool == "partprobe":
        return False, "no verifier yet confirms that the planned partition nodes exist and match the disk identity"
    if tool == "udevadm":
        return False, "udev settle completion does not prove that the expected partition nodes are present"
    if tool.startswith("mkfs"):
        device = step.command[-1]
        if not Path(device).exists():
            return False, f"{device} does not exist after formatting"
        # blkid is the authority on what a device now contains.
        result = default_runner([
            "/run/current-system/profile/sbin/blkid",
            "-o",
            "value",
            "-s",
            "TYPE",
            device,
        ])
        fstype = (result.stdout or "").strip()
        expected = {"mkfs.ext4": "ext4", "mkfs.btrfs": "btrfs", "mkfs.xfs": "xfs", "mkfs.fat": "vfat"}
        want = expected.get(tool, "")
        if result.returncode != 0 or not fstype:
            return False, f"blkid could not report a filesystem on {device}"
        if want and fstype != want:
            return False, f"{device} holds {fstype}, expected {want}"
        return True, f"{device} holds {fstype}"
    if tool == "mount":
        device, target = step.command[1], step.command[2]
        mounts = read_text("/proc/mounts")
        if not any(line.split()[0] == device and len(line.split()) > 1 and line.split()[1] == target
                   for line in mounts.splitlines()):
            return False, f"{device} is not mounted at {target}"
        return True, f"{device} mounted at {target}"
    if tool == "mkdir":
        target = step.command[-1]
        if not Path(target).is_dir():
            return False, f"{target} was not created"
        return True, f"{target} exists"
    return False, "no verifier registered for this step"


def execute(
    steps: Sequence[Step],
    disk: str,
    acknowledgement: str | None = None,
    dry_run: bool = True,
    runner: Runner = default_runner,
    verifier: Verifier = default_verifier,
    out: Callable[[str], None] | None = None,
) -> list[StepResult]:
    """Run the steps in order, or refuse before touching anything."""
    emit = out or (lambda line: print(line, file=sys.stderr))
    results: list[StepResult] = []

    if not dry_run:
        if acknowledgement != disk:
            raise ExecutorError(
                "execute.acknowledgement",
                f"running for real requires an acknowledgement naming {disk!r} "
                f"(got {acknowledgement!r})",
            )
        if not any(step.destructive for step in steps):
            raise ExecutorError(
                "execute.no-destructive-steps",
                "refusing a real run that has nothing destructive to do; the plan looks wrong",
            )
        raise ExecutorError(
            "execute.not-enabled",
            "real disk execution is disabled: the executor does not yet bind the plan to "
            "a revalidated block-device identity, repeat consent before each destructive "
            "step, or verify GPT/partition/udev state",
        )

    for index, step in enumerate(steps, start=1):
        printable = " ".join(step.command)
        result = StepResult(step.command, step.purpose, step.destructive, "planned")

        if dry_run:
            result.status = "skipped"
            result.detail = "dry run"
            results.append(result)
            emit(f"[{index}/{len(steps)}] would run: {printable}")
            continue

        emit(f"[{index}/{len(steps)}] running: {printable}")
        completed = runner(step.command)
        if completed.returncode != 0:
            result.status = "failed"
            result.detail = (completed.stderr or "").strip()[:300] or f"exit {completed.returncode}"
            results.append(result)
            emit(f"  failed: {result.detail}")
            raise ExecutorError("execute.step-failed", f"{printable}: {result.detail}")

        ok, detail = verifier(step)
        if not ok:
            result.status = "unverified"
            result.detail = detail
            results.append(result)
            emit(f"  unverified: {detail}")
            raise ExecutorError("execute.step-unverified", f"{printable}: {detail}")

        result.status = "done"
        result.detail = detail
        results.append(result)
        emit(f"  ok: {detail}")

    return results
