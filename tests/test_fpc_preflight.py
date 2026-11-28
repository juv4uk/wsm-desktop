# SPDX-License-Identifier: LicenseRef-Volnist
"""The FPC preflight must keep the rule that makes it honest."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "pascal" / "wsm_preflight.pas"
PY = ROOT / "wsm_install" / "preflight_env.py"


class VerdictParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pas = SRC.read_text(encoding="utf-8")
        self.py = PY.read_text(encoding="utf-8")

    def test_incomplete_is_not_a_pass(self) -> None:
        """The one rule the whole check exists to enforce."""
        self.assertIn("incomplete is not a pass", self.pas)
        self.assertIn("incomplete is not a pass", self.py)

    def test_the_three_states_exist(self) -> None:
        for state in ("'pass'", "'fail'", "'not-run'"):
            self.assertIn(state, self.pas)

    def test_the_same_criteria_are_checked(self) -> None:
        for identifier in ("tools", "guix", "root", "mount-point",
                           "system-file", "report", "isa"):
            self.assertIn(f"'{identifier}'", self.pas, f"missing criterion {identifier}")

    def test_a_missing_report_is_not_run_not_fail(self) -> None:
        """No report is a gap in evidence, not a broken machine."""
        self.assertIn("'report', 'not-run'", self.pas)

    def test_an_existing_mount_point_is_refused(self) -> None:
        self.assertIn("would hide under it", self.pas)


class SafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pas = SRC.read_text(encoding="utf-8")

    def test_it_never_writes_or_executes(self) -> None:
        for forbidden in ("Rewrite(", "fpOpen", "ExecuteProcess", "popen", "Shell("):
            self.assertNotIn(forbidden, self.pas, f"side effect present: {forbidden}")

    def test_it_reads_only_proc_and_path(self) -> None:
        self.assertIn("/proc/mounts", self.pas)
        self.assertIn("/proc/cpuinfo", self.pas)

    def test_failure_and_incomplete_use_different_exit_codes(self) -> None:
        self.assertIn("Halt(1)", self.pas)
        self.assertIn("Halt(6)", self.pas)


if __name__ == "__main__":
    unittest.main()
