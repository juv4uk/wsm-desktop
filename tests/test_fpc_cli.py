# SPDX-License-Identifier: LicenseRef-Volnist
"""The FPC frontend may execute its own readers - and nothing else."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "pascal" / "wsm_install.pas"


class ExecutionBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SRC.read_text(encoding="utf-8")

    def test_it_never_uses_a_shell(self) -> None:
        """A shell would turn a path with a semicolon into a second command."""
        for forbidden in ("/bin/sh", "ExecuteProcess(", "popen", "Shell("):
            self.assertNotIn(forbidden, self.text, f"shell path present: {forbidden}")

    def test_it_executes_only_its_sibling_readers(self) -> None:
        for tool in ("wsm-preflight", "wsm-hwcheck", "wsm-classify", "wsm-partition"):
            self.assertIn(f"'{tool}'", self.text)
        # The one program it must never invoke. Check the code, not the prose
        # that explains why it is absent.
        code = "\n".join(
            line.split("//")[0] for line in self.text.splitlines()
            if not line.strip().startswith("{") and not line.strip().startswith("}")
        )
        self.assertNotIn("'sgdisk'", code)

    def test_it_declares_that_nothing_was_applied(self) -> None:
        self.assertIn('"applied":false', self.text)
        self.assertIn("Nothing was applied", self.text)


class OrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SRC.read_text(encoding="utf-8")

    def test_preflight_runs_first(self) -> None:
        self.assertLess(self.text.index("'wsm-preflight'"),
                        self.text.index("'wsm-hwcheck'"))

    def test_a_failed_preflight_stops_everything(self) -> None:
        self.assertIn("nothing else was run", self.text)

    def test_incomplete_is_not_treated_as_a_pass(self) -> None:
        self.assertIn("incomplete, which is not a pass", self.text)
        self.assertIn("ExitIncomplete", self.text)

    def test_a_supplied_report_is_not_replaced_by_a_probe(self) -> None:
        self.assertIn("if ReportPath = '' then", self.text)


class NoDeadCodeTests(unittest.TestCase):
    def test_no_unused_shell_helper_remains(self) -> None:
        self.assertNotIn("RunTool(", SRC.read_text(encoding="utf-8").replace("RunToolCode(", ""))


if __name__ == "__main__":
    unittest.main()
