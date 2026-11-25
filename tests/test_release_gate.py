# SPDX-License-Identifier: LicenseRef-Volnist
"""The gate must never call a skipped check a pass."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from release_gate import check_channels, check_image, check_tests, criterion, from_exit, verdict  # noqa: E402


class VerdictTests(unittest.TestCase):
    def test_all_pass_is_a_pass(self) -> None:
        self.assertEqual(verdict([criterion("a", "pass", "")])["overall"], "pass")

    def test_any_failure_fails(self) -> None:
        self.assertEqual(
            verdict([criterion("a", "pass", ""), criterion("b", "fail", "")])["overall"],
            "fail",
        )

    def test_a_skipped_check_makes_it_incomplete(self) -> None:
        """This is the whole point: silence is not success."""
        result = verdict([criterion("a", "pass", ""), criterion("b", "not-run", "no qemu")])
        self.assertEqual(result["overall"], "incomplete")

    def test_failure_outranks_incomplete(self) -> None:
        result = verdict([criterion("a", "not-run", ""), criterion("b", "fail", "")])
        self.assertEqual(result["overall"], "fail")


class ExitMappingTests(unittest.TestCase):
    def test_could_not_start_a_check_is_not_run(self) -> None:
        self.assertEqual(from_exit("x", -1, "python unavailable")["status"], "not-run")

    def test_child_exit_127_is_a_failure(self) -> None:
        self.assertEqual(from_exit("x", 127, "child returned 127")["status"], "fail")

    def test_zero_is_pass(self) -> None:
        self.assertEqual(from_exit("x", 0, "")["status"], "pass")

    def test_nonzero_is_fail(self) -> None:
        self.assertEqual(from_exit("x", 1, "")["status"], "fail")


class TestRunnerTests(unittest.TestCase):
    def test_test_suite_uses_one_bounded_unittest_discovery_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tests").mkdir()
            (root / "tests" / "test_sample.py").write_text("pass\n", encoding="utf-8")
            with patch("release_gate.ROOT", root), patch(
                "release_gate.run", return_value=(0, "OK")
            ) as run_mock:
                result = check_tests()
        self.assertEqual(result["status"], "pass")
        self.assertEqual(run_mock.call_count, 1)
        command = run_mock.call_args.args[0]
        self.assertEqual(command[1:6], ["-m", "unittest", "discover", "-s", "tests"])
        self.assertIn("-v", command)
        self.assertEqual(run_mock.call_args.kwargs["timeout"], 900)


class ChannelGateTests(unittest.TestCase):
    def test_missing_compatibility_lock_is_not_configured_not_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch("release_gate.ROOT", root), patch(
                "release_gate.run", return_value=(0, "Free structural policy passed")
            ) as run_check:
                result = check_channels()
        self.assertEqual(result["status"], "not-run")
        self.assertIn("Compatibility: NOT_CONFIGURED", result["detail"])
        self.assertIn("no Compatibility product claim", result["detail"])
        run_check.assert_called_once()

    def test_missing_required_free_lock_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch("release_gate.ROOT", root), patch("release_gate.run") as run_mock:
                result = check_channels()
        self.assertEqual(result["status"], "fail")
        self.assertIn("required Free lock is missing", result["detail"])
        run_mock.assert_not_called()

    def test_invalid_configured_compatibility_lock_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "channels.compatibility.lock.scm").write_text(
                "(list)", encoding="utf-8"
            )
            with patch("release_gate.ROOT", root), patch(
                "release_gate.run",
                side_effect=[
                    (0, "Free structural policy passed"),
                    (1, "Compatibility lock violates structural policy"),
                ],
            ) as run_check:
                result = check_channels()
        self.assertEqual(result["status"], "fail")
        self.assertIn("Compatibility lock violates structural policy", result["detail"])
        self.assertEqual(run_check.call_count, 2)

    def test_free_lock_failure_fails_before_optional_compatibility(self) -> None:
        with patch("release_gate.run", return_value=(1, "Free lock is invalid")) as run_check:
            result = check_channels()
        self.assertEqual(result["status"], "fail")
        self.assertIn("Free lock is invalid", result["detail"])
        run_check.assert_called_once()

    def test_configured_compatibility_lock_is_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "channels.compatibility.lock.scm").write_text(
                "(list)", encoding="utf-8"
            )
            with patch("release_gate.ROOT", root), patch(
                "release_gate.run",
                side_effect=[
                    (0, "Free structural policy passed"),
                    (0, "Compatibility structural policy passed"),
                ],
            ) as run_check:
                result = check_channels()
        self.assertEqual(result["status"], "pass")
        self.assertIn("configured Compatibility", result["detail"])
        self.assertEqual(run_check.call_count, 2)


class ImageTests(unittest.TestCase):
    IDS = ("checksum", "manifest", "iso-structure", "boot-bios", "boot-uefi")

    @staticmethod
    def payload(overall: str) -> dict:
        status = {"pass": "pass", "fail": "fail", "incomplete": "not-run"}[overall]
        return {
            "schema": "wsm-release-verdict/1",
            "artifact": "wsm.iso",
            "overall": overall,
            "criteria": [
                {"id": item, "status": status, "detail": f"{item}: {status}"}
                for item in ImageTests.IDS
            ],
        }

    def run_nested(self, payload: dict, exit_code: int):
        completed = subprocess.CompletedProcess(
            args=["verify_live_release.py"],
            returncode=exit_code,
            stdout=json.dumps(payload),
            stderr="",
        )
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "wsm.iso"
            iso.write_bytes(b"synthetic fixture")
            with patch("release_gate.subprocess.run", return_value=completed):
                return check_image(iso, boot=True)

    def test_no_iso_is_recorded_as_not_run(self) -> None:
        self.assertEqual(check_image(None, boot=False)["status"], "not-run")

    def test_missing_iso_file_fails(self) -> None:
        self.assertEqual(check_image(Path("/nonexistent/image.iso"), boot=False)["status"], "fail")

    def test_nested_incomplete_with_exit_zero_is_not_run(self) -> None:
        result = self.run_nested(self.payload("incomplete"), 0)
        self.assertEqual(result["status"], "not-run")
        self.assertIn("boot-bios", result["detail"])

    def test_nested_full_pass_requires_every_criterion(self) -> None:
        result = self.run_nested(self.payload("pass"), 0)
        self.assertEqual(result["status"], "pass")

    def test_nested_fail_is_preserved(self) -> None:
        result = self.run_nested(self.payload("fail"), 1)
        self.assertEqual(result["status"], "fail")

    def test_nested_missing_criterion_fails_closed(self) -> None:
        payload = self.payload("pass")
        payload["criteria"].pop()
        result = self.run_nested(payload, 0)
        self.assertEqual(result["status"], "fail")
        self.assertIn("criteria mismatch", result["detail"])

    def test_nested_malformed_status_fails_closed(self) -> None:
        for malformed in ([], {}):
            with self.subTest(malformed=malformed):
                payload = self.payload("pass")
                payload["criteria"][0]["status"] = malformed
                result = self.run_nested(payload, 0)
                self.assertEqual(result["status"], "fail")
                self.assertIn("invalid status", result["detail"])


class CliTests(unittest.TestCase):
    def test_gate_emits_a_verdict_and_returns_incomplete_exit_code(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "release_gate.py"), "--skip-tests", "--compact"],
            capture_output=True, text=True, check=False, cwd=ROOT,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["schema"], "wsm-release-gate/1")
        # A missing check is not a successful release gate.
        self.assertEqual(payload["overall"], "incomplete")
        self.assertEqual(completed.returncode, 2)
        ids = {item["id"] for item in payload["criteria"]}
        self.assertIn("channels", ids)
        self.assertIn("image", ids)


if __name__ == "__main__":
    unittest.main()
