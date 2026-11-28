# SPDX-License-Identifier: LicenseRef-Volnist
"""Policy tests for trusted failure reporting in GitHub Actions workflows."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
GUIX_EVALUATOR = WORKFLOWS / "guix-profile-evaluation.yml"
TRUSTED_REPORTER = WORKFLOWS / "trusted-ci-failure-reporter.yml"
TRUSTED_WORKFLOWS = {CI, GUIX_EVALUATOR}
REPORTS = re.compile(r"gh api .*commits/\$GITHUB_SHA/comments|gh pr comment|gh issue comment")


def document_of(workflow: Path) -> dict:
    try:
        import yaml
    except ModuleNotFoundError:  # pragma: no cover - CI installs pyyaml
        raise unittest.SkipTest("pyyaml is not installed")
    # BaseLoader keeps the GitHub Actions on key as a string.
    return yaml.load(workflow.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def steps_of(workflow: Path) -> list[dict]:
    document = document_of(workflow)
    result: list[dict] = []
    for job in (document.get("jobs") or {}).values():
        result.extend(job.get("steps") or [])
    return result


def all_jobs_disabled(workflow: Path) -> bool:
    """A workflow whose every job is statically disabled cannot fail at runtime."""
    jobs = (document_of(workflow).get("jobs") or {})
    return bool(jobs) and all(
        str(job.get("if", "")).strip() in {"${{ false }}", "false"}
        for job in jobs.values()
    )


def inline_failure_reporter(workflow: Path) -> bool:
    """Detect an inline comment writer; used for PR-controlled write-policy checks."""
    return any(
        "failure()" in str(step.get("if", ""))
        and REPORTS.search(str(step.get("run", "")))
        for step in steps_of(workflow)
    )


def inline_summary_reporter(workflow: Path) -> bool:
    """Accept a read-only GitHub step summary as a visible failure report."""
    return any(
        "failure()" in str(step.get("if", ""))
        and "$GITHUB_STEP_SUMMARY" in str(step.get("run", ""))
        for step in steps_of(workflow)
    )


def exact_open_main_prs(
    candidates: list[dict],
    *,
    repository: str,
    head_sha: str,
    head_branch: str,
) -> list[int]:
    """Model the reporter's final live-PR predicate for policy edge cases."""
    return [
        item["number"]
        for item in candidates
        if isinstance(item.get("number"), int)
        and item.get("state") == "open"
        and (item.get("base") or {}).get("ref") == "main"
        and ((item.get("base") or {}).get("repo") or {}).get("full_name") == repository
        and ((item.get("head") or {}).get("repo") or {}).get("full_name") == repository
        and (item.get("head") or {}).get("ref") == head_branch
        and (item.get("head") or {}).get("sha") == head_sha
    ]


def pr(
    number: int,
    *,
    repository: str = "juv4uk/wsm-desktop",
    head_sha: str = "a" * 40,
    head_branch: str = "fix/example",
    base_branch: str = "main",
    state: str = "open",
    head_repository: str | None = None,
) -> dict:
    return {
        "number": number,
        "state": state,
        "base": {
            "ref": base_branch,
            "repo": {"full_name": repository},
        },
        "head": {
            "ref": head_branch,
            "sha": head_sha,
            "repo": {"full_name": head_repository or repository},
        },
    }


class CiFailureVisibilityTests(unittest.TestCase):
    def test_ci_and_guix_evaluator_have_no_inline_write_reporter(self) -> None:
        for workflow in sorted(TRUSTED_WORKFLOWS):
            with self.subTest(workflow=workflow.name):
                document = document_of(workflow)
                self.assertEqual(document.get("permissions"), {"contents": "read"})
                self.assertFalse(
                    inline_failure_reporter(workflow),
                    f"{workflow.name} is PR-controlled and must not write a comment",
                )

    def test_trusted_reporter_runs_from_default_branch_workflow_run(self) -> None:
        reporter = document_of(TRUSTED_REPORTER)
        trigger = (reporter.get("on") or {}).get("workflow_run") or {}
        self.assertEqual(
            trigger.get("workflows"),
            ["CI", "Guix profile evaluation"],
        )
        self.assertEqual(trigger.get("types"), ["completed"])
        self.assertEqual(reporter.get("permissions"), {})
        self.assertEqual(set((reporter.get("jobs") or {}).keys()), {"report-failure"})
        gate = str(reporter["jobs"]["report-failure"].get("if", ""))
        self.assertIn("refs/heads/main", gate)
        self.assertIn("workflow_run.conclusion", gate)
        self.assertIn("workflow_run.event", gate)

    def test_trusted_reporter_has_minimal_permissions_and_no_untrusted_execution(self) -> None:
        reporter = document_of(TRUSTED_REPORTER)
        job = reporter["jobs"]["report-failure"]
        self.assertEqual(
            job.get("permissions"),
            {"actions": "read", "pull-requests": "read", "issues": "write"},
        )
        steps = job.get("steps") or []
        self.assertEqual(len(steps), 1)
        self.assertNotIn("uses", steps[0])
        script = str(steps[0].get("run", ""))
        for forbidden in (
            "actions/checkout",
            "download-artifact",
            "upload-artifact",
            "git fetch",
            "gh pr checkout",
        ):
            self.assertNotIn(forbidden, script)
        self.assertNotIn("commits/$GITHUB_SHA/comments", script)

    def test_reporter_validates_workflow_and_source_identity(self) -> None:
        reporter = document_of(TRUSTED_REPORTER)
        script = "\n".join(
            str(step.get("run", ""))
            for step in reporter["jobs"]["report-failure"].get("steps") or []
        )
        for required in (
            "actions/runs/$RUN_ID",
            ".github/workflows/ci.yml",
            ".github/workflows/guix-profile-evaluation.yml",
            ".head_repository.full_name",
            ".head_branch",
            ".head_sha",
            ".workflow_id",
            ".path == $path",
            ".event //",
            ".conclusion //",
            "RUN_EVENT",
            "RUN_CONCLUSION",
            '== "pull_request"',
            '== "failure"',
            "git check-ref-format",
        ):
            self.assertIn(required, script)

    def test_reporter_revalidates_exact_main_pr_and_uses_fallback_lookup(self) -> None:
        reporter = document_of(TRUSTED_REPORTER)
        script = "\n".join(
            str(step.get("run", ""))
            for step in reporter["jobs"]["report-failure"].get("steps") or []
        )
        for required in (
            ".pull_requests[]?",
            '.state == "open"',
            '.base.ref == "main"',
            ".base.repo.full_name == $repo",
            ".head.repo.full_name == $repo",
            ".head.ref == $branch",
            ".head.sha == $sha",
            "gh api --method GET --paginate",
            '-f head="$REPOSITORY_OWNER:$RUN_HEAD_BRANCH"',
            "-f base=main",
            "MATCHED_PR_NUMBERS",
            "-ne 1",
            "issues/$PR_NUMBER/comments",
        ):
            self.assertIn(required, script)

    def test_pr_predicate_accepts_one_exact_current_main_pr(self) -> None:
        current = pr(17)
        self.assertEqual(
            exact_open_main_prs(
                [current],
                repository="juv4uk/wsm-desktop",
                head_sha="a" * 40,
                head_branch="fix/example",
            ),
            [17],
        )

    def test_pr_predicate_rejects_stale_sha(self) -> None:
        candidate = pr(17, head_sha="b" * 40)
        self.assertEqual(
            exact_open_main_prs(
                [candidate],
                repository="juv4uk/wsm-desktop",
                head_sha="a" * 40,
                head_branch="fix/example",
            ),
            [],
        )

    def test_pr_predicate_rejects_closed_fork_and_wrong_base(self) -> None:
        candidates = [
            pr(1, state="closed"),
            pr(2, head_repository="someone/fork"),
            pr(3, base_branch="release"),
        ]
        self.assertEqual(
            exact_open_main_prs(
                candidates,
                repository="juv4uk/wsm-desktop",
                head_sha="a" * 40,
                head_branch="fix/example",
            ),
            [],
        )

    def test_fallback_requires_exactly_one_match(self) -> None:
        one = [pr(7)]
        multiple = [pr(7), pr(8)]
        none: list[dict] = []
        args = {
            "repository": "juv4uk/wsm-desktop",
            "head_sha": "a" * 40,
            "head_branch": "fix/example",
        }
        self.assertEqual(len(exact_open_main_prs(one, **args)), 1)
        self.assertEqual(len(exact_open_main_prs(multiple, **args)), 2)
        self.assertEqual(len(exact_open_main_prs(none, **args)), 0)

    def test_other_workflows_keep_their_existing_failure_reporting(self) -> None:
        missing = [
            workflow.name
            for workflow in sorted(WORKFLOWS.glob("*.yml"))
            if workflow not in TRUSTED_WORKFLOWS | {TRUSTED_REPORTER}
            and not all_jobs_disabled(workflow)
            and not inline_failure_reporter(workflow)
            and not inline_summary_reporter(workflow)
        ]
        self.assertEqual(
            missing,
            [],
            "these workflows fail without leaving a readable cause: " + ", ".join(missing),
        )

    def test_only_substitutes_is_disabled_by_the_accepted_adr(self) -> None:
        substitutes = WORKFLOWS / "substitutes.yml"
        archives = WORKFLOWS / "package-archives.yml"
        self.assertTrue(all_jobs_disabled(substitutes))
        self.assertFalse(all_jobs_disabled(archives))
        self.assertTrue(inline_failure_reporter(archives))

    def test_substitutes_workflow_does_not_silently_run(self) -> None:
        workflow = document_of(WORKFLOWS / "substitutes.yml")
        self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})
        self.assertEqual(str(workflow["jobs"]["publish"].get("if")), "false")


    def test_scan_finds_all_three_trusted_workflow_files(self) -> None:
        self.assertTrue(CI.is_file())
        self.assertTrue(GUIX_EVALUATOR.is_file())
        self.assertTrue(TRUSTED_REPORTER.is_file())
        self.assertGreaterEqual(len(list(WORKFLOWS.glob("*.yml"))), 3)


if __name__ == "__main__":
    unittest.main()
