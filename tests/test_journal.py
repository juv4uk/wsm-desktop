# SPDX-License-Identifier: LicenseRef-Volnist
"""Journal storage and recovery reporting; no disk executor is wired to it."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wsm_install.journal import Journal, read_entries, recovery_report


class JournalStorageTests(unittest.TestCase):
    def test_writer_records_start_and_finish_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            journal = Journal(path)
            journal.starting(
                1, 2, ["/run/current-system/profile/sbin/partprobe", "/dev/nvme0n1"],
                "re-read partition table",
            )
            journal.finished(1, "done", "postcondition observed")
            entries = read_entries(path)

        self.assertEqual([entry["event"] for entry in entries],
                         ["step-starting", "step-finished"])
        self.assertEqual(entries[0]["index"], 1)
        self.assertEqual(entries[0]["command"][-1], "/dev/nvme0n1")
        self.assertEqual(entries[1]["status"], "done")
        self.assertTrue(all(entry.get("schema") for entry in entries))

    def test_writer_records_abort_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            journal = Journal(path)
            journal.aborted("postcondition did not match")
            entries = read_entries(path)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["event"], "aborted")
        self.assertEqual(entries[0]["reason"], "postcondition did not match")

    def test_journal_is_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            journal = Journal(path)
            journal.aborted("first")
            journal.aborted("second")
            entries = read_entries(path)
        self.assertEqual([entry["reason"] for entry in entries], ["first", "second"])

    def test_truncated_last_line_is_ignored(self) -> None:
        """A crash mid-write must not make the complete prior journal unreadable."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            Journal(path).aborted("complete")
            with path.open("a", encoding="utf-8") as handle:
                handle.write('{"event": "step-star')
            entries = read_entries(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["reason"], "complete")

    def test_non_object_json_line_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            path.write_text('[]\n{"event":"aborted","reason":"safe"}\n', encoding="utf-8")
            entries = read_entries(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["reason"], "safe")


class RecoveryReportTests(unittest.TestCase):
    def make_journal(self, directory: Path, entries: list[dict]) -> Path:
        path = directory / "journal.jsonl"
        path.write_text(
            "\n".join(json.dumps(entry) for entry in entries) + "\n",
            encoding="utf-8",
        )
        return path

    def test_missing_journal_says_do_not_assume_anything(self) -> None:
        report = recovery_report(Path("/nonexistent/wsm-install.jsonl"))
        self.assertIn("Do not assume the disk is untouched", report)

    def test_report_lists_completed_and_failed_steps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self.make_journal(Path(temporary), [
                {"event": "step-starting", "index": 1, "total": 2,
                 "command": ["/usr/sbin/partprobe", "/dev/x"], "purpose": ""},
                {"event": "step-finished", "index": 1, "status": "done", "detail": "ok"},
                {"event": "step-starting", "index": 2, "total": 2,
                 "command": ["/usr/sbin/mkfs.ext4", "/dev/x1"], "purpose": ""},
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
                {"event": "step-starting", "index": 1, "total": 2,
                 "command": ["/usr/bin/mount", "/dev/x", "/mnt"], "purpose": ""},
            ])
            report = recovery_report(path)
        self.assertIn("never reported back", report)
        self.assertIn("may be in any state", report)

    def test_report_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self.make_journal(Path(temporary), [
                {"event": "aborted", "reason": "interrupted"},
            ])
            before = path.read_bytes()
            recovery_report(path)
            after = path.read_bytes()
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
