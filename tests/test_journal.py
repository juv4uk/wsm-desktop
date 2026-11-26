# SPDX-License-Identifier: LicenseRef-Volnist
"""A half-finished install must leave a readable trace, not a guess."""

from __future__ import annotations

import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.executor import ExecutorError, execute  # noqa: E402
from wsm_install.install_steps import Step  # noqa: E402
from wsm_install.journal import Journal, read_entries, recovery_report  # noqa: E402

STEPS = [
    Step(["/usr/sbin/partprobe", "/dev/nvme0n1"], "re-read"),
    Step(["/usr/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p2"], "format root", destructive=True),
    Step(["/usr/bin/mount", "/dev/nvme0n1p2", "/mnt"], "mount root"),
]


class ApplyDisabledJournalTests(unittest.TestCase):
    def test_apply_is_refused_before_journal_file_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            with self.assertRaises(ExecutorError) as caught:
                execute(STEPS, "/dev/nvme0n1", dry_run=False)
            self.assertEqual(caught.exception.code, "execute.apply-disabled")
            self.assertFalse(path.exists())

    def test_executor_has_no_runner_verifier_acknowledgement_or_journal_api(self) -> None:
        parameters = set(inspect.signature(execute).parameters)
        self.assertEqual(parameters, {"steps", "disk", "dry_run", "out"})
        self.assertTrue({"starting", "finished", "aborted"}.issubset(set(dir(Journal))))

    def test_dry_run_writes_no_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            execute(STEPS, "/dev/nvme0n1", dry_run=True, out=lambda _: None)
            self.assertFalse(path.exists())


class JournalUtilityTests(unittest.TestCase):
    def test_journal_is_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            journal = Journal(path)
            journal.aborted("first")
            journal.aborted("second")
            entries = read_entries(path)
        self.assertEqual([e["reason"] for e in entries], ["first", "second"])

    def test_truncated_last_line_is_ignored(self) -> None:
        """A crash mid-write must not make the whole journal unreadable."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            journal = Journal(path)
            journal.aborted("complete")
            with path.open("a", encoding="utf-8") as handle:
                handle.write('{"event": "step-star')
            entries = read_entries(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["reason"], "complete")


class RecoveryReportTests(unittest.TestCase):
    def make_journal(self, directory: Path, entries: list[dict]) -> Path:
        path = directory / "journal.jsonl"
        path.write_text(
            "\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8"
        )
        return path

    def test_missing_journal_says_do_not_assume_anything(self) -> None:
        report = recovery_report(Path("/nonexistent/journal.jsonl"))
        self.assertIn("Do not assume the disk is untouched", report)

    def test_report_lists_completed_and_failed_steps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self.make_journal(Path(temporary), [
                {"event": "step-starting", "index": 1, "total": 3, "command": ["/usr/sbin/partprobe", "/dev/x"], "purpose": ""},
                {"event": "step-finished", "index": 1, "status": "done", "detail": "ok"},
                {"event": "step-starting", "index": 2, "total": 3, "command": ["/usr/sbin/mkfs.ext4", "/dev/x1"], "purpose": ""},
                {"event": "step-finished", "index": 2, "status": "failed", "detail": "disk on fire"},
                {"event": "aborted", "reason": "mkfs failed"},
            ])
            report = recovery_report(path)
        self.assertIn("Steps that completed", report)
        self.assertIn("partprobe", report)
        self.assertIn("Steps that failed", report)
        self.assertIn("disk on fire", report)
        self.assertIn("Do not rerun the installer", report)

    def test_interrupted_step_is_called_out(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self.make_journal(Path(temporary), [
                {"event": "step-starting", "index": 1, "total": 2, "command": ["/usr/bin/mount", "/dev/x", "/mnt"], "purpose": ""},
            ])
            report = recovery_report(path)
        self.assertIn("never reported back", report)
        self.assertIn("may be in any state", report)


if __name__ == "__main__":
    unittest.main()
