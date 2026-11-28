# SPDX-License-Identifier: LicenseRef-Volnist
"""Failure comments for PR runs must be emitted by trusted default-branch code."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def document(path: Path) -> dict:
    try:
        import yaml
    except ModuleNotFoundError:  # pragma: no cover - CI installs pyyaml
        raise unittest.SkipTest("pyyaml is not installed")
    parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    # PyYAML's YAML 1.1 loader treats the GitHub key "on" as boolean True.
    if "on" not in parsed and True in parsed:
        parsed["on"] = parsed[True]
    return parsed


def steps_of(job: dict) -> list[dict]:
    return job.get("steps") or []


class CiFailureVisibilityTests(unittest.TestCase):
    def test_pr_ci_and_guix_evaluator_have_no_comment_write_permission(self) -> None:
        for filename in ("ci.yml", "guix-profile-evaluation.yml"):
            workflow = document(WORKFLOWS / filename)
            permissions = workflow.get("permissions") or {}
            self.assertNotIn("issues", permissions, filename)
            self.assertNotIn("pull-requests", permissions, filename)
            for job in (workflow.get("jobs") or {}).values():
                for step in steps_of(job):
                    script = str(step.get("run", ""))
                    self.assertNotIn("GH_TOKEN", script, filename)
                    self.assertNotIn("gh api", script, filename)

    def test_trusted_reporter_is_a_separate_workflow_run_workflow(self) -> None:
        workflow = document(WORKFLOWS / "trusted-pr-failure-reporter.yml")
        trigger = workflow.get("on", {}).get("workflow_run", {})
        self.assertEqual(
            trigger.get("workflows"),
            ["CI", "Guix profile evaluation"],
        )
        self.assertEqual(trigger.get("types"), ["completed"])
        self.assertEqual(workflow.get("permissions"), {})

        reporter = (workflow.get("jobs") or {})["report-pr-failure"]
        self.assertEqual(
            reporter.get("permissions"),
            {"actions": "read", "pull-requests": "read", "issues": "write"},
        )
        condition = str(reporter.get("if", ""))
        for required in ("conclusion", "failure", "pull_request", "431025036", "431678119"):
            self.assertIn(required, condition)

        steps = steps_of(reporter)
        self.assertEqual(len(steps), 1)
        self.assertNotIn("uses", steps[0])
        script = str(steps[0].get("run", ""))
        self.assertIn("actions/runs/$SOURCE_RUN_ID", script)
        self.assertIn("pulls?state=all&head=", script)
        self.assertIn("head.sha == $sha", script)
        self.assertIn("issues/$PR_NUMBER/comments", script)
        self.assertIn("HEAD_REPOSITORY", script)
        self.assertIn("SOURCE_WORKFLOW_NAME", script)
        self.assertIn("GITHUB_REPOSITORY", script)
        self.assertNotIn("actions/checkout", script)
        self.assertNotIn("download-artifact", script)
        self.assertNotIn("workflow_run.pull_requests", script)

    def test_release_workflow_reporter_is_confined_to_trusted_main_triggers(self) -> None:
        workflow = document(WORKFLOWS / "release-minimal-live.yml")
        trigger = workflow.get("on", {})
        self.assertEqual((trigger.get("push") or {}).get("branches"), ["main"])
        self.assertIn("workflow_dispatch", trigger)


if __name__ == "__main__":
    unittest.main()
