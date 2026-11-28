# SPDX-License-Identifier: LicenseRef-Volnist
"""Policy tests for trusted failure reporting in GitHub Actions workflows."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
GUIX_EVALUATOR = WORKFLOWS / "guix-profile-evaluation.yml"
GUIX_REPORTER = WORKFLOWS / "guix-profile-failure-reporter.yml"


def document_of(workflow: Path) -> dict:
    try:
        import yaml
    except ModuleNotFoundError:  # pragma: no cover - CI installs pyyaml
        raise unittest.SkipTest("pyyaml is not installed")
    return yaml.load(workflow.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def trigger_of(document: dict) -> dict:
    """BaseLoader keeps the GitHub-specific on key as a string."""
    return document.get("on") or {}


def inline_failure_reporter(workflow: Path) -> bool:
    document = document_of(workflow)
    for job in (document.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if "failure()" in str(step.get("if", "")):
                run = str(step.get("run", ""))
                if "gh api" in run or "gh pr comment" in run:
                    return True
    return False


class CiFailureVisibilityTests(unittest.TestCase):
    def test_guix_evaluator_is_read_only_and_does_not_comment(self) -> None:
        evaluator = document_of(GUIX_EVALUATOR)
        self.assertEqual(evaluator.get("permissions"), {"contents": "read"})
        for job in (evaluator.get("jobs") or {}).values():
            permissions = job.get("permissions") or {}
            self.assertNotIn("issues", permissions)
            self.assertNotIn("pull-requests", permissions)
            self.assertFalse(any(
                "gh api" in str(step.get("run", ""))
                for step in (job.get("steps") or [])
            ))

    def test_reporter_uses_workflow_run_from_the_default_branch(self) -> None:
        reporter = document_of(GUIX_REPORTER)
        workflow_run = trigger_of(reporter).get("workflow_run") or {}
        self.assertEqual(workflow_run.get("workflows"), ["Guix profile evaluation"])
        self.assertEqual(workflow_run.get("types"), ["completed"])
        self.assertEqual(reporter.get("permissions"), {})
        self.assertEqual(set((reporter.get("jobs") or {}).keys()), {"report-failure"})
        gate = str(reporter["jobs"]["report-failure"].get("if", ""))
        self.assertIn("github.ref == 'refs/heads/main'", gate)

    def test_reporter_has_only_minimum_scoped_permissions(self) -> None:
        reporter = document_of(GUIX_REPORTER)
        job = reporter["jobs"]["report-failure"]
        self.assertEqual(
            job.get("permissions"),
            {"actions": "read", "pull-requests": "read", "issues": "write"},
        )
        gate = str(job.get("if", ""))
        self.assertIn("workflow_run.conclusion", gate)
        self.assertIn("workflow_run.event", gate)

    def test_reporter_validates_run_identity_and_pr_association(self) -> None:
        reporter = document_of(GUIX_REPORTER)
        steps = reporter["jobs"]["report-failure"].get("steps") or []
        self.assertEqual(len(steps), 1)
        self.assertNotIn("uses", steps[0])
        script = str(steps[0].get("run", ""))
        self.assertIn("actions/workflows/guix-profile-evaluation.yml", script)
        self.assertIn("actions/runs/$RUN_ID", script)
        self.assertIn(".workflow_id == $workflow_id", script)
        self.assertIn('.path == ".github/workflows/guix-profile-evaluation.yml"', script)
        self.assertIn('.conclusion == "failure"', script)
        self.assertIn(".head.sha == $sha", script)
        self.assertIn('.base.ref == "main"', script)
        self.assertIn(".base.repo.full_name == $repo", script)
        self.assertIn("^[1-9][0-9]*$", script)
        self.assertIn("issues/$PR_NUMBER/comments", script)

    def test_reporter_never_checks_out_or_downloads_untrusted_content(self) -> None:
        reporter = document_of(GUIX_REPORTER)
        steps = reporter["jobs"]["report-failure"].get("steps") or []
        all_steps = str(steps)
        for forbidden in ("actions/checkout", "download-artifact", "upload-artifact"):
            self.assertNotIn(forbidden, all_steps)
        self.assertFalse(any("uses" in step for step in steps))
        self.assertNotIn("git fetch", all_steps)
        self.assertNotIn("gh pr checkout", all_steps)

    def test_other_workflows_keep_their_existing_failure_reporting(self) -> None:
        excluded = {GUIX_EVALUATOR, GUIX_REPORTER}
        missing = [
            workflow.name
            for workflow in sorted(WORKFLOWS.glob("*.yml"))
            if workflow not in excluded and not inline_failure_reporter(workflow)
        ]
        self.assertEqual(
            missing,
            [],
            "these workflows fail without leaving a readable cause: " + ", ".join(missing),
        )

    def test_scan_finds_the_expected_workflows(self) -> None:
        self.assertTrue(GUIX_EVALUATOR.is_file())
        self.assertTrue(GUIX_REPORTER.is_file())
        self.assertGreaterEqual(len(list(WORKFLOWS.glob("*.yml"))), 3)


if __name__ == "__main__":
    unittest.main()
