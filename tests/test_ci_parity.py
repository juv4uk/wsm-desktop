# SPDX-License-Identifier: LicenseRef-Volnist
"""Every script invoked by make check-* must also run unconditionally in CI.

The repository already refuses a check target that make check never runs
(tests/test_makefile_coverage.py). This extends that rule to the CI boundary:
a script that CI only mentions in a comment, step name, or conditional step is
not actually part of the green check result.
"""

from __future__ import annotations

import re
import shlex
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"
CI = ROOT / ".github" / "workflows" / "ci.yml"

TARGET = re.compile(r"^(check-[a-z0-9-]+):\n((?:\t.*\n)+)", re.MULTILINE)
SCRIPT = re.compile(r"\$\(PYTHON\) (scripts/[\w./-]+\.py)")


def scripts_run_by_make_check() -> dict[str, list[str]]:
    """Script path -> the check targets that invoke it."""
    found: dict[str, list[str]] = {}
    text = MAKEFILE.read_text(encoding="utf-8")
    for match in TARGET.finditer(text):
        target, body = match.group(1), match.group(2)
        for script in SCRIPT.findall(body):
            found.setdefault(script, []).append(target)
    return found


def scripts_run_by_ci(
    workflow_text: str,
) -> dict[str, list[tuple[str, int, bool]]]:
    """Return actual Python script commands and whether their steps are conditional."""
    document = yaml.safe_load(workflow_text)
    if not isinstance(document, dict) or not isinstance(document.get("jobs"), dict):
        raise AssertionError("CI workflow has no jobs mapping")

    found: dict[str, list[tuple[str, int, bool]]] = {}
    for job_name, job in document["jobs"].items():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps", [])
        if not isinstance(steps, list):
            continue
        for index, step in enumerate(steps):
            if not isinstance(step, dict) or not isinstance(step.get("run"), str):
                continue
            tokens = shlex.split(step["run"], comments=True)
            for position, token in enumerate(tokens[:-1]):
                if Path(token).name not in {"python", "python3"}:
                    continue
                script = tokens[position + 1]
                if script.startswith("scripts/") and script.endswith(".py"):
                    found.setdefault(script, []).append(
                        (str(job_name), index, "if" in step)
                    )
    return found


class CiParityTests(unittest.TestCase):
    def test_every_make_check_script_runs_unconditionally_in_ci(self) -> None:
        ci = scripts_run_by_ci(CI.read_text(encoding="utf-8"))
        missing: dict[str, list[str]] = {}
        conditional: dict[str, list[str]] = {}

        for script, targets in scripts_run_by_make_check().items():
            records = ci.get(script, [])
            if not records:
                missing[script] = targets
            elif not any(not is_conditional for _, _, is_conditional in records):
                conditional[script] = targets

        self.assertEqual(
            missing,
            {},
            "these scripts run in make check but have no Python command in CI: "
            + ", ".join(
                f"{script} ({', '.join(targets)})"
                for script, targets in missing.items()
            ),
        )
        self.assertEqual(
            conditional,
            {},
            "these scripts are only in conditional CI steps: "
            + ", ".join(
                f"{script} ({', '.join(targets)})"
                for script, targets in conditional.items()
            ),
        )

    def test_the_audit_finds_scripts_on_both_sides(self) -> None:
        """If either parser stops matching, parity must not pass vacuously."""
        self.assertGreaterEqual(len(scripts_run_by_make_check()), 4)
        ci = scripts_run_by_ci(CI.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(ci), 4)

    def test_comments_and_step_names_are_not_ci_execution(self) -> None:
        workflow = """
jobs:
  checks:
    steps:
      - name: python scripts/check_only_in_name.py
        run: echo "this step does not run a Python check"
"""
        self.assertNotIn(
            "scripts/check_only_in_name.py",
            scripts_run_by_ci(workflow),
        )

    def test_conditional_python_step_is_detected_as_conditional(self) -> None:
        workflow = """
jobs:
  checks:
    steps:
      - if: false
        run: python scripts/conditional_check.py
"""
        records = scripts_run_by_ci(workflow)
        self.assertEqual(
            records["scripts/conditional_check.py"],
            [("checks", 0, True)],
        )


if __name__ == "__main__":
    unittest.main()
