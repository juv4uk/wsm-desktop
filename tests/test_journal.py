# SPDX-License-Identifier: LicenseRef-Volnist
"""Journal serialization/recovery format tests; no real disk APPLY is active."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wsm_install.journal import Journal, read_entries, recovery_report


class JournalWritingTests(unittest.TestCase):
    def test_each_step_can_be_recorded_before_and_after(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            journal = Journal(path)
            for index, command in enumerate((
                ["/run/current-system/profile/sbin/partprobe", "/dev/nvme0n1"],
                ["/run/current-system/profile/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p2"],
                ["/run/current-system/profile/bin/mount", "/dev/nvme0n1p2", "/mnt"],
            ), start=1):
                journal.starting(index, 3, command, "synthetic recovery fixture")
                journal.finished(index, "done", "synthetic postcondition")
            entries = read_entries(path)
        events = [entry["event"] for entry in entries]
        self.assertEqual(events.count("step-starting"), 3)
        self.assertEqual(events.count("step-finished"), 3)
        self.assertTrue(all(
            entry["status"] == "done"
            for entry in entries if entry["event"] == "step-finished"
        ))

    def test_failure_is_recorded_with_the_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            journal = Journal(path)
            journal.starting(1, 1, ["/run/current-system/profile/sbin/mkfs.ext4", "/dev/vda2"], "format")
            journal.finished(1, "failed", "synthetic failure")
            journal.aborted("synthetic failure")
            entries = read_entries(path)
        aborted = [entry for entry in entries if entry["event"] == "aborted"]
        self.assertEqual(len(aborted), 1)
        self.assertIn("synthetic", aborted[0]["reason"])

    def test_journal_is_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            journal = Journal(path)
            journal.aborted("first")
            journal.aborted("second")
            entries = read_entries(path)
        self.assertEqual([entry["reason"] for entry in entries], ["first", "second"])

    def test_truncated_last_line_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            journal = Journal(path)
            journal.aborted("complete")
            with path.open("a", encoding="utf-8") as stream:
                stream.write('{"event": "step-star')
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
