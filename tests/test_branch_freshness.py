# SPDX-License-Identifier: LicenseRef-Volnist
"""The drift reporter must measure, and must never fail an honest branch."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_branch_freshness import ahead_count, behind_count, main, verdict  # noqa: E402


def git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *arguments],
        cwd=root, check=True, capture_output=True,
    )


class MeasurementTests(unittest.TestCase):
    def build(self, directory: Path) -> Path:
        git(directory, "init", "-q", "-b", "main")
        (directory / "a").write_text("1", encoding="utf-8")
        git(directory, "add", "-A")
        git(directory, "commit", "-q", "-m", "one")
        git(directory, "branch", "topic")
        for name in ("b", "c", "d"):
            (directory / name).write_text("x", encoding="utf-8")
            git(directory, "add", "-A")
            git(directory, "commit", "-q", "-m", name)
        return directory

    def test_a_fresh_branch_is_zero_behind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.build(Path(tmp))
            # Branch created at the current tip, not at the first commit.
            git(repo, "branch", "fresh")
            self.assertEqual(behind_count(repo, "main", "fresh"), 0)

    def test_drift_is_counted_from_the_base_side(self) -> None:
        """Three commits on main after the branch: the branch is 3 behind."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.build(Path(tmp))
            self.assertEqual(behind_count(repo, "main", "topic"), 3)
            self.assertEqual(ahead_count(repo, "main", "topic"), 0)


class VerdictTests(unittest.TestCase):
    def test_up_to_date(self) -> None:
        self.assertIn("up to date", verdict(0, 5, 20))

    def test_small_drift_asks_for_a_rebase(self) -> None:
        self.assertIn("rebase before", verdict(5, 1, 20))

    def test_large_drift_says_it_will_conflict(self) -> None:
        message = verdict(148, 2, 20)
        self.assertIn("148", message)
        self.assertIn("will conflict", message)


class NeverFailsTests(unittest.TestCase):
    """A gate that blocks honest work gets bypassed; this one only reports."""

    def test_drift_does_not_change_the_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = MeasurementTests().build(Path(tmp))
            code = main(["--root", str(repo), "--base", "main", "--head", "topic"])
        self.assertEqual(code, 0)

    def test_a_missing_base_is_reported_not_crashed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = MeasurementTests().build(Path(tmp))
            code = main(["--root", str(repo), "--base", "no-such-branch", "--head", "topic"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
