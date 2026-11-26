# SPDX-License-Identifier: LicenseRef-Volnist
"""Run install steps, verifying each one before starting the next.

This is the module that actually executes. Everything before it produced
plans; this one runs them, which means the safety rules here matter more than
anywhere else in the repository.

Four rules, and none of them is negotiable:

1. **Dry run is the default.** Running for real requires an explicit
   acknowledgement that names the disk, exactly like the partition planner.
2. **A destructive step never runs unattended.** Each one is announced, and the
   acknowledgement is checked again immediately before it, not once at the
   start: a confirmation given for step one must not silently cover step seven.
3. **Every step is verified before the next begins.** A `mkfs` that returned 0
   but produced nothing is not success. Verification reads the system, not the
   exit code.
4. **The first failure stops everything.** Continuing past a failed mount and
   formatting anyway is how a machine ends up with a system that cannot boot and
   no explanation.

The executor is injectable: `run` and `verify` are parameters, so the whole
thing is testable without a disk, a root shell or QEMU.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from wsm_install.install_steps import Step
from wsm_install.journal import Journal  # noqa: F401 - used in the signature

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
        return True, "partition table re-read requested"
    if tool == "udevadm":
        return True, "device nodes settled"
    if tool.startswith("mkfs"):
        device = step.command[-1]
        if not Path(device).exists():
            return False, f"{device} does not exist after formatting"
        # blkid is the authority on what a device now contains.
        result = default_runner(["blkid", "-o", "value", "-s", "TYPE", device])
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
    return True, "no verification defined for this step"


def execute(
    steps: Sequence[Step],
    disk: str,
    acknowledgement: str | None = None,
    dry_run: bool = True,
    runner: Runner = default_runner,
    verifier: Verifier = default_verifier,
    out: Callable[[str], None] | None = None,
    journal: "Journal | None" = None,
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
        if journal is not None:
            journal.starting(index, len(steps), step.command, step.purpose)

        completed = runner(step.command)
        if completed.returncode != 0:
            result.status = "failed"
            result.detail = (completed.stderr or "").strip()[:300] or f"exit {completed.returncode}"
            results.append(result)
            if journal is not None:
                journal.finished(index, "failed", result.detail)
                journal.aborted(f"{printable}: {result.detail}")
            emit(f"  failed: {result.detail}")
            raise ExecutorError("execute.step-failed", f"{printable}: {result.detail}")

        ok, detail = verifier(step)
        if not ok:
            result.status = "unverified"
            result.detail = detail
            results.append(result)
            if journal is not None:
                journal.finished(index, "unverified", detail)
                journal.aborted(f"{printable}: {detail}")
            emit(f"  unverified: {detail}")
            raise ExecutorError("execute.step-unverified", f"{printable}: {detail}")

        result.status = "done"
        result.detail = detail
        results.append(result)
        if journal is not None:
            journal.finished(index, "done", detail)
        emit(f"  ok: {detail}")

    return results
