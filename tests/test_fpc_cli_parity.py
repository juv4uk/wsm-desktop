# SPDX-License-Identifier: LicenseRef-Volnist
"""Behavioural tests for scripts/check_fpc_cli_parity.py.

The harness is the only thing standing between "the Pascal front end exists"
and "the Pascal front end decides the same way as the Python one", so it gets
tested like any other component rather than trusted because it is new.

Two kinds of evidence here:

* unit tests of the pure comparison logic (``judge``, ``normalise_stderr_line``),
  driven with synthetic observations — no subprocess, no binary;
* one end-to-end test of ``--self-test``, which runs the harness against mocked
  front ends and requires it to notice a lie. If that mode is ever weakened,
  this test fails.

Nothing here claims the Pascal binary compiles. It cannot: there is no FPC in
the authoring environment. That claim belongs to
``.github/workflows/fpc-install-cli.yml``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_fpc_cli_parity import (  # noqa: E402
    CASES,
    CLASSIFY,
    EXIT_BLOCKED,
    EXIT_OK,
    EXIT_REFUSED,
    PREFLIGHT,
    Observation,
    build_reports,
    judge,
    normalise_stderr_line,
)

HARNESS = ROOT / "scripts" / "check_fpc_cli_parity.py"


def case_named(name: str):
    for case in CASES:
        if case.name == name:
            return case
    raise AssertionError(f"no case named {name}")


class CaseTableTests(unittest.TestCase):
    """The table is the contract, so its shape is asserted, not assumed."""

    def test_the_table_covers_every_required_report_kind(self) -> None:
        names = {case.name for case in CASES}
        for required in (
            "valid-1.0.0",
            "missing-required-field",
            "unsupported-version",
            "wrong-gpu-identity",
            "malformed-json",
        ):
            with self.subTest(required=required):
                self.assertIn(required, names)

    def test_both_read_only_modes_are_exercised(self) -> None:
        self.assertEqual({PREFLIGHT, CLASSIFY}, {"preflight", "classify"})

    def test_blocked_is_a_plan_outcome_and_not_a_classification_outcome(self) -> None:
        """A report that blocks a plan still classifies; the exit codes differ."""
        blocked = case_named("blocked-critical-evidence")
        self.assertEqual(blocked.expectations(PREFLIGHT)[0], EXIT_BLOCKED)
        self.assertEqual(blocked.expectations(CLASSIFY), (EXIT_OK, ""))

    def test_a_refused_report_is_refused_in_both_modes(self) -> None:
        refused = case_named("unsupported-version")
        preflight_exit, preflight_line = refused.expectations(PREFLIGHT)
        classify_exit, classify_line = refused.expectations(CLASSIFY)
        self.assertEqual(preflight_exit, EXIT_REFUSED)
        self.assertEqual(classify_exit, EXIT_REFUSED)
        self.assertEqual(preflight_line, classify_line)

    def test_exactly_one_documented_strictness_is_allowed(self) -> None:
        """Refusing more than Python is a decision; it must be a listed one."""
        stricter = [case.name for case in CASES if case.allow_stricter_pascal]
        self.assertEqual(stricter, ["half-gpu-identity-pair"])

    def test_build_reports_materialises_the_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            written = build_reports(Path(temporary))
            self.assertEqual(set(written), {case.name for case in CASES})
            self.assertEqual(
                written["malformed-json"].read_text(encoding="utf-8"), "{broken"
            )
            broken = json.loads(written["wrong-gpu-identity"].read_text(encoding="utf-8"))
            gpu = [item for item in broken["devices"] if item["category"] == "gpu"][0]
            self.assertEqual(gpu["identity"]["device_id"], "zzzz")
            missing = json.loads(
                written["missing-required-field"].read_text(encoding="utf-8")
            )
            self.assertNotIn("report_id", missing)


class NormalisationTests(unittest.TestCase):
    """Only implementation-language text may be dropped, nothing else."""

    def test_decoder_wording_is_dropped(self) -> None:
        self.assertEqual(
            normalise_stderr_line(
                "wsm-install: invalid report JSON: Expecting value: line 1 column 2"
            ),
            "wsm-install: invalid report JSON",
        )

    def test_the_decision_itself_is_never_dropped(self) -> None:
        line = (
            "wsm-install: unsupported hardware report schema '9.0.0'; "
            "supported: 1.0.0, 1.1.0"
        )
        self.assertEqual(normalise_stderr_line(line), line)

    def test_schema_error_location_is_part_of_the_decision(self) -> None:
        line = "wsm-install: schema error at devices.6.identity.device_id: 'zzzz' does not match"
        self.assertEqual(normalise_stderr_line(line), line)

    def test_argparse_wrapping_is_dropped_but_the_error_is_kept(self) -> None:
        self.assertEqual(
            normalise_stderr_line("usage: wsm-install [-h] [--version] --report PATH"),
            "usage: wsm-install",
        )
        self.assertEqual(
            normalise_stderr_line("wsm-install: error: --preflight is required"),
            "wsm-install: error",
        )


def honest_python(case, mode=PREFLIGHT) -> Observation:
    """What the Python CLI is recorded as doing, as an observation."""
    exit_code, stderr_first = case.expectations(mode)
    return Observation(exit_code, stderr_first)


class JudgeTests(unittest.TestCase):
    """The comparison rules, driven directly."""

    def test_identical_observations_agree(self) -> None:
        case = case_named("valid-1.0.0")
        python = honest_python(case)
        verdict = judge(case, PREFLIGHT, python, python)
        self.assertTrue(verdict.ok, verdict.detail)
        self.assertFalse(verdict.documented_strictness)

    def test_pascal_accepting_a_report_python_refuses_is_a_failure(self) -> None:
        """The fail-open direction: more permission is never a documented delta."""
        case = case_named("missing-required-field")
        python = honest_python(case)
        verdict = judge(
            case,
            PREFLIGHT,
            python,
            Observation(EXIT_OK, python.stderr_first),
        )
        self.assertFalse(verdict.ok)
        self.assertIn("exit codes differ", verdict.detail)

    def test_documented_strictness_passes_and_is_reported(self) -> None:
        case = case_named("half-gpu-identity-pair")
        python = honest_python(case)
        verdict = judge(
            case,
            PREFLIGHT,
            python,
            Observation(EXIT_REFUSED, "wsm-install: the GPU identity pair is incomplete"),
        )
        self.assertTrue(verdict.ok, verdict.detail)
        self.assertTrue(verdict.documented_strictness)

    def test_strictness_is_not_granted_to_a_case_that_did_not_ask(self) -> None:
        case = case_named("valid-1.0.0")
        python = honest_python(case)
        verdict = judge(
            case,
            PREFLIGHT,
            python,
            Observation(EXIT_REFUSED, "wsm-install: something stricter"),
        )
        self.assertFalse(verdict.ok)
        self.assertIn("exit codes differ", verdict.detail)

    def test_a_binary_that_did_not_run_is_a_failure(self) -> None:
        case = case_named("valid-1.0.0")
        verdict = judge(
            case,
            PREFLIGHT,
            honest_python(case),
            Observation(None, "", error="cannot run"),
        )
        self.assertFalse(verdict.ok)
        self.assertIn("did not run", verdict.detail)

    def test_python_contract_drift_is_reported_as_such(self) -> None:
        """If the Python CLI changes, that is named, not blamed on Pascal."""
        case = case_named("unsupported-version")
        exit_code, stderr_first = case.expectations(PREFLIGHT)
        verdict = judge(
            case,
            PREFLIGHT,
            Observation(EXIT_OK, stderr_first),
            Observation(EXIT_OK, stderr_first),
        )
        self.assertFalse(verdict.ok)
        self.assertIn("python contract drift", verdict.detail)

    def test_a_changed_first_stderr_line_alone_is_a_failure(self) -> None:
        case = case_named("wrong-gpu-identity")
        python = honest_python(case)
        verdict = judge(
            case,
            PREFLIGHT,
            python,
            Observation(python.exit_code, "wsm-install: schema error at $: something else"),
        )
        self.assertFalse(verdict.ok)
        self.assertIn("stderr differs", verdict.detail)


class SelfTestTests(unittest.TestCase):
    """The harness' own self-test must run and must pass."""

    def test_self_test_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(HARNESS), "--self-test"],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(ROOT),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("self-test passed", completed.stdout)

    def test_the_harness_refuses_to_call_one_side_a_parity_check(self) -> None:
        """`--python-only` is explicit; omitting --pascal is an error."""
        completed = subprocess.run(
            [sys.executable, str(HARNESS), "--python", sys.executable],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(ROOT),
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("--pascal is required", completed.stderr)


if __name__ == "__main__":
    unittest.main()
