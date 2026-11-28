# SPDX-License-Identifier: LicenseRef-Volnist
"""Failure reports must be readable without giving PR-controlled YAML a write token."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
GUIX_EVALUATOR = "guix-profile-evaluation.yml"
GUIX_REPORTER = "guix-evaluation-failure-reporter.yml"

# Existing non-Guix workflows use their own failure-reporting steps. Guix is
# special: its write-capable reporter must be a separate workflow_run workflow.
REPORTS = re.compile(
    r"gh api .*commits/\\$GITHUB_SHA/comments|gh pr comment|gh issue comment"
)


def document_of(workflow: Path) -> dict:
    try:
        import yaml
    except ModuleNotFoundError:  # pragma: no cover - CI installs pyyaml
        raise unittest.SkipTest("pyyaml is not installed")
    # BaseLoader keeps the YAML key "on" as a string (YAML 1.1 safe_load
    # otherwise treats it as a boolean).
    return yaml.load(workflow.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def steps_of(workflow: Path) -> list[dict]:
    found: list[dict] = []
    for job in (document_of(workflow).get("jobs") or {}).values():
        found.extend(job.get("steps") or [])
    return found


def reporting_steps(workflow: Path) -> list[dict]:
    return [
        step
        for step in steps_of(workflow)
        if "failure()" in str(step.get("if", ""))
        and REPORTS.search(str(step.get("run", "")))
    ]


class CiFailureVisibilityTests(unittest.TestCase):
    def test_non_guix_workflows_leave_a_readable_failure_reason(self) -> None:
        exempt = {GUIX_EVALUATOR, GUIX_REPORTER}
        missing = [
            workflow.name
            for workflow in sorted(WORKFLOWS.glob("*.yml"))
            if workflow.name not in exempt and not reporting_steps(workflow)
        ]
        self.assertEqual(
            missing,
            [],
            "these workflows fail without leaving a readable cause: " + ", ".join(missing),
        )

    def test_guix_evaluator_has_no_write_permission_or_inline_reporter(self) -> None:
        workflow = WORKFLOWS / GUIX_EVALUATOR
        document = document_of(workflow)
        self.assertEqual(document.get("permissions"), {"contents": "read"})
        self.assertNotIn("pull-requests", document.get("permissions") or {})

        all_steps = steps_of(workflow)
        self.assertFalse(
            any(REPORTS.search(str(step.get("run", ""))) for step in all_steps),
            "PR-controlled Guix evaluator YAML must not receive or use a write-capable reporter token",
        )
        self.assertFalse(
            any("issues" in (job.get("permissions") or {}) for job in document["jobs"].values()),
            "the Guix evaluator job must remain read-only",
        )

    def test_guix_reporter_runs_only_after_the_default_branch_workflow_completes(self) -> None:
        workflow = WORKFLOWS / GUIX_REPORTER
        document = document_of(workflow)
        self.assertEqual(set(document.get("on", {})), {"workflow_run"})
        trigger = document["on"]["workflow_run"]
        self.assertEqual(trigger.get("workflows"), ["Guix profile evaluation"])
        self.assertEqual(trigger.get("types"), ["completed"])
        self.assertEqual(document.get("permissions"), {})

        jobs = document.get("jobs") or {}
        self.assertEqual(set(jobs), {"report"})
        job = jobs["report"]
        self.assertIn("failure()", str(job.get("if", "")))
        self.assertIn("pull_request", str(job.get("if", "")))
        self.assertEqual(job.get("permissions"), {"actions": "read", "issues": "write"})

        steps = job.get("steps") or []
        uses = [str(step.get("uses", "")) for step in steps]
        self.assertFalse(any("checkout" in action for action in uses))
        self.assertFalse(any("download-artifact" in action for action in uses))
        self.assertFalse(any("upload-artifact" in action for action in uses))

        script = "\\n".join(str(step.get("run", "")) for step in steps)
        for required in (
            "actions/runs/$RUN_ID",
            "431678119",
            ".github/workflows/guix-profile-evaluation.yml",
            "Guix profile evaluation",
            "RUN_EVENT",
            "pull_request",
            "RUN_CONCLUSION",
            "failure",
            ".pull_requests[]?",
            ".base.ref == \\"main\\"",
            "issues/$PR_NUMBER/comments",
        ):
            self.assertIn(required, script)
        self.assertNotIn("commits/$GITHUB_SHA/comments", script)
        self.assertNotIn("actions/download-artifact", script)
        self.assertNotIn("git checkout", script.lower())

    def test_the_scan_is_not_empty(self) -> None:
        """If the glob stopped matching, the tests above must not pass vacuously."""
        self.assertGreaterEqual(len(list(WORKFLOWS.glob("*.yml"))), 3)

    def test_the_rule_catches_a_workflow_without_a_reporting_step(self) -> None:
        sample = (
            "name: sample\\n"
            "on: push\\n"
            "jobs:\\n"
            "  build:\\n"
            "    runs-on: ubuntu-24.04\\n"
            "    steps:\\n"
            "      - name: build\\n"
            "        run: echo hi\\n"
        )
        path = WORKFLOWS / "_tmp_sample.yml"
        path.write_text(sample, encoding="utf-8")
        try:
            self.assertEqual(reporting_steps(path), [])
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
