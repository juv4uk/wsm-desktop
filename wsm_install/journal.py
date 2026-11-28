# SPDX-License-Identifier: LicenseRef-Volnist
"""An append-only record of what the installer actually did.

The executor stops at the first failure, which is right. But stopping is not the
same as knowing: after a failed `mkfs` the disk is in a state nobody wrote down,
and the next person to look at it has to guess.

This journal is that record. Every step is written twice - once before it runs
and once after - and each line is flushed to disk, so a crash between steps
leaves a readable trace rather than an empty file.

Why a journal and not a rollback:

* rollback of a half-written disk is not generally possible, and pretending
  otherwise is worse than saying "here is exactly what happened";
* the honest recovery for a failed install is: know what ran, verify the disk,
  and start again from a known state;
* a journal is also the input for a bug report that can be acted on.

The recovery report is deliberately explicit about what it does *not* know.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "wsm-install-journal/1"
DEFAULT_JOURNAL = Path("/var/log/wsm-install.jsonl")


class Journal:
    """Append-only JSONL writer. Every entry is flushed before returning."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, entry: dict[str, Any]) -> None:
        entry = dict(entry)
        entry.setdefault("at", dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        entry.setdefault("schema", SCHEMA)
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
        # O_APPEND + fsync: a crash must not lose the line that says what happened.
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, line.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def start_plan(self, plan_digest: str, disk: str) -> None:
        """Record which plan this journal belongs to, before the first step.

        Without this the journal says what happened but not what it was supposed to
        happen to: two runs against the same disk look alike even when their plans
        differ by one argument. The digest is the same value consent is bound to, so
        a later reader can tell whether the steps recorded here were the steps that
        were approved.
        """
        self._append({
            "event": "plan-bound",
            "plan_digest": plan_digest,
            "disk": disk,
        })

    def starting(
        self,
        index: int,
        total: int,
        command: Iterable[str],
        purpose: str,
        step_digest: str | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "event": "step-starting",
            "index": index,
            "total": total,
            "command": list(command),
            "purpose": purpose,
        }
        if step_digest is not None:
            entry["step_digest"] = step_digest
        self._append(entry)

    def finished(self, index: int, status: str, detail: str) -> None:
        self._append({
            "event": "step-finished",
            "index": index,
            "status": status,
            "detail": detail,
        })

    def aborted(self, reason: str) -> None:
        self._append({"event": "aborted", "reason": reason})


def read_entries(path: Path) -> list[dict[str, Any]]:
    """Read a journal, ignoring a truncated last line from a crash mid-write."""
    try:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        # A valid JSON line that is not an object is still not a journal entry;
        # keeping it would make every reader defend against it separately.
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def recovery_report(path: Path) -> str:
    """Describe the state a half-finished install left behind, honestly."""
    entries = read_entries(path)
    if not entries:
        return (
            "No journal entries were found.\n"
            "Either nothing was attempted, or the journal path is wrong.\n"
            "Do not assume the disk is untouched: verify it before retrying.\n"
        )

    started: dict[int, dict[str, Any]] = {}
    finished: dict[int, dict[str, Any]] = {}
    aborted = None
    for entry in entries:
        event = entry.get("event")
        if event == "step-starting":
            started[entry.get("index")] = entry
        elif event == "step-finished":
            finished[entry.get("index")] = entry
        elif event == "aborted":
            aborted = entry

    lines: list[str] = ["Installation did not complete.", ""]

    done = [index for index, entry in finished.items() if entry.get("status") == "done"]
    failed = [index for index, entry in finished.items() if entry.get("status") in {"failed", "unverified"}]
    unknown = [index for index in started if index not in finished]

    if done:
        lines.append("Steps that completed:")
        for index in sorted(done):
            lines.append(f"  {index}. {' '.join(started[index]['command'])}")
        lines.append("")

    if failed:
        lines.append("Steps that failed:")
        for index in sorted(failed):
            entry = finished[index]
            lines.append(f"  {index}. {' '.join(started[index]['command'])}")
            lines.append(f"     reason: {entry.get('detail', 'unknown')}")
        lines.append("")

    if unknown:
        lines.append("Steps that started and never reported back:")
        for index in sorted(unknown):
            lines.append(f"  {index}. {' '.join(started[index]['command'])}")
        lines.append("  These were interrupted mid-run; the disk may be in any state.")
        lines.append("")

    if aborted:
        lines.append(f"Installer stopped: {aborted.get('reason', 'unknown reason')}")
        lines.append("")

    lines.append("What to do next:")
    lines.append("  1. Do not rerun the installer on this disk yet.")
    lines.append("  2. Inspect it: lsblk, blkid, and check for mounted filesystems.")
    lines.append("  3. Filesystems that were formatted hold no data; there is nothing to recover from them.")
    lines.append("  4. Once the state is understood, rerun from a known starting point.")
    return "\n".join(lines) + "\n"
