# SPDX-License-Identifier: LicenseRef-Volnist
"""Every workflow must leave a readable reason when it fails.

`docs/ECOSYSTEM-PRINCIPLES.md` forbids leaving a pipeline failure with no cause
in a place that can be read without authorisation: task logs need auth, so an
agent without it sees only "Process completed with exit code 2" and spends a
whole run guessing.

The principle was written after exactly that happened, and only the release
workflow implemented it. `ci.yml` and `guix-profile-evaluation.yml` did not —
the second one being a 180-minute Guix evaluation, where guessing is most
expensive.

So the rule is checked, not remembered.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# Something that writes where a reader without auth can see it.
REPORTS = re.compile(r"gh api .*?(?:commits/\$GITHUB_SHA/comments|issues/\$PR_NUMBER/comments)|gh pr comment|gh issue comment")


def document_of(workflow: Path) -> dict:
    text = workflow.read_text(encoding="utf-8")
    try:
        import yaml
    except ModuleNotFoundError:  # pragma: no cover - CI installs pyyaml
        raise unittest.SkipTest("pyyaml is not installed")
    return yaml.safe_load(text)


def has_failure_reporter(workflow: Path) -> bool:
    jobs = (document_of(workflow).get("jobs") or {}).values()
    for job in jobs:
        job_if = str(job.get("if", ""))
        steps = job.get("steps") or []
        if "failure()" in job_if and any(
            REPORTS.search(str(step.get("run", ""))) for step in steps
        ):
            return True
        if any(
            "failure()" in str(step.get("if", ""))
            and REPORTS.search(str(step.get("run", "")))
            for step in steps
        ):
            return True
    return False


class CiFailureVisibilityTests(unittest.TestCase):
    def test_every_workflow_reports_its_failure(self) -> None:
        missing = [
            workflow.name
            for workflow in sorted(WORKFLOWS.glob("*.yml"))
            if not has_failure_reporter(workflow)
        ]
        self.assertEqual(
            missing,
            [],
            "these workflows fail without leaving a readable cause: " + ", ".join(missing),
        )

    def test_guix_failure_reporter_isolated_from_untrusted_evaluation(self) -> None:
        workflow = WORKFLOWS / "guix-profile-evaluation.yml"
        jobs = document_of(workflow).get("jobs") or {}
        evaluate = jobs["evaluate-locked-profiles"]
        reporter = jobs["report-failure"]

        self.assertNotIn("issues", evaluate.get("permissions") or {})
        self.assertEqual(reporter.get("permissions"), {"issues": "write"})
        self.assertIn("failure()", str(reporter.get("if", "")))
        self.assertNotIn("actions/checkout", str(reporter.get("steps", [])))
        reporter_script = "\\n".join(
            str(step.get("run", "")) for step in reporter.get("steps", [])
        )
        self.assertIn("issues/$PR_NUMBER/comments", reporter_script)
        self.assertNotIn("commits/$GITHUB_SHA/comments", reporter_script)

    def test_the_scan_is_not_empty(self) -> None:
        """If the glob stopped matching, the test above would pass vacuously."""
        self.assertGreaterEqual(len(list(WORKFLOWS.glob("*.yml"))), 2)

    def test_the_rule_catches_a_workflow_without_a_reporting_step(self) -> None:
        sample = (
            "name: sample\n"
            "on: push\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-24.04\n"
            "    steps:\n"
            "      - name: build\n"
            "        run: echo hi\n"
        )
        path = WORKFLOWS / "_tmp_sample.yml"
        path.write_text(sample, encoding="utf-8")
        try:
            self.assertFalse(has_failure_reporter(path))
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
