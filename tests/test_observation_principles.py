# SPDX-License-Identifier: LicenseRef-Volnist
"""Every verdict has three states, not two.

`unknown ≠ false` is the shared principle across the WSM repositories
(docs/OBSERVATION-PRINCIPLES.md). The failure it prevents is specific: a check
that never ran quietly becomes "checked and fine". These tests make that
impossible to introduce by accident.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Modules that produce a verdict and must therefore know about "not run".
VERDICT_MODULES = [
    "scripts/release_gate.py",
    "scripts/verify_live_release.py",
    "wsm_install/preflight_env.py",
    "wsm_install/executor.py",
    "wsm_install/profile.py",
]

THIRD_STATE = ("not-run", "not_run", "not-assessed", "not_assessed", "unknown", "unverified")


class ThirdStateTests(unittest.TestCase):
    def test_every_verdict_module_knows_a_third_state(self) -> None:
        for relative in VERDICT_MODULES:
            text = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(module=relative):
                self.assertTrue(
                    any(state in text for state in THIRD_STATE),
                    f"{relative} has no third state; 'did not run' would become 'passed'",
                )

    def test_verdicts_do_not_collapse_to_a_boolean(self) -> None:
        """A `bool` verdict cannot express 'not checked', so it is not allowed here."""
        offenders: list[str] = []
        for relative in VERDICT_MODULES:
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name in {"verdict", "criterion"}:
                    returns_bool = any(
                        isinstance(child, ast.Return)
                        and isinstance(child.value, ast.Constant)
                        and isinstance(child.value.value, bool)
                        for child in ast.walk(node)
                    )
                    if returns_bool:
                        offenders.append(f"{relative}:{node.name}")
        self.assertEqual(offenders, [], f"boolean verdicts found: {offenders}")


class HardwareUnknownTests(unittest.TestCase):
    def test_report_schema_allows_unknown_discovery(self) -> None:
        import json

        schema = json.loads(
            (ROOT / "schemas" / "hardware-report.schema.json").read_text(encoding="utf-8")
        )
        text = json.dumps(schema)
        self.assertIn("unknown", text)
        self.assertIn("not-run", text)

    def test_profile_evidence_requires_not_assessed(self) -> None:
        """A bundle claiming nothing is unverified is not evidence."""
        import json

        schema = json.loads(
            (ROOT / "schemas" / "profile-evidence.schema.json").read_text(encoding="utf-8")
        )
        self.assertIn("not_assessed", schema["required"])
        self.assertGreaterEqual(schema["properties"]["not_assessed"]["minItems"], 1)


class DocumentationTests(unittest.TestCase):
    def test_principles_are_documented_and_attributed(self) -> None:
        text = (ROOT / "docs" / "OBSERVATION-PRINCIPLES.md").read_text(encoding="utf-8")
        self.assertIn("ecosystem-observer", text)
        self.assertIn("unknown ≠ false", text)
        self.assertIn("Спостереження ≠ судження", text)


if __name__ == "__main__":
    unittest.main()
