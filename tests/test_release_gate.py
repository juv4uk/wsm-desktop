# SPDX-License-Identifier: LicenseRef-Volnist
"""The gate must never turn a missing check into a release PASS."""

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

from release_gate import (  # noqa: E402
    check_channels,
    check_image,
    criterion,
    exit_status,
    from_exit,
    verdict,
)


class VerdictTests(unittest.TestCase):
    def test_all_pass_is_a_pass(self) -> None:
        self.assertEqual(verdict([criterion("a", "pass", "")])["overall"], "pass")

    def test_any_failure_fails(self) -> None:
        self.assertEqual(
            verdict([criterion("a", "pass", ""), criterion("b", "fail", "")])["overall"],
            "fail",
        )

    def test_a_skipped_check_makes_it_incomplete(self) -> None:
        result = verdict([criterion("a", "pass", ""), criterion("b", "not-run", "no qemu")])
        self.assertEqual(result["overall"], "incomplete")

    def test_failure_outranks_incomplete(self) -> None:
        result = verdict([criterion("a", "not-run", ""), criterion("b", "fail", "")])
        self.assertEqual(result["overall"], "fail")

    def test_process_exit_distinguishes_all_verdicts(self) -> None:
        self.assertEqual(exit_status("pass"), 0)
        self.assertEqual(exit_status("fail"), 1)
        self.assertEqual(exit_status("incomplete"), 2)


class ExitMappingTests(unittest.TestCase):
    def test_unable_to_start_a_check_is_not_run(self) -> None:
        self.assertEqual(from_exit("x", -1, "python unavailable")["status"], "not-run")

    def test_child_exit_127_is_a_real_failure(self) -> None:
        self.assertEqual(from_exit("x", 127, "child returned 127")["status"], "fail")

    def test_zero_is_pass(self) -> None:
        self.assertEqual(from_exit("x", 0, "")["status"], "pass")

    def test_nonzero_is_fail(self) -> None:
        self.assertEqual(from_exit("x", 1, "")["status"], "fail")


class ChannelTests(unittest.TestCase):
    def test_missing_compatibility_lock_is_not_run_and_never_reuses_free_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "channels.lock.scm").write_text("(list free)", encoding="utf-8")
            with (
                patch("release_gate.ROOT", root),
                patch("release_gate.run", return_value=(0, "structural policy passed")) as run_mock,
            ):
                result = check_channels()

        self.assertEqual(result["status"], "not-run")
        self.assertIn("channels.compatibility.lock.scm", result["detail"])
        self.assertEqual(run_mock.call_count, 1)
        args = run_mock.call_args.args[0]
        self.assertIn("--policy", args)
        self.assertIn("free", args)
        self.assertIn("--lock", args)
        self.assertEqual(Path(args[args.index("--lock") + 1]).name, "channels.lock.scm")

    def test_each_configured_policy_uses_its_own_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            free_lock = root / "channels.lock.scm"
            compatibility_lock = root / "channels.compatibility.lock.scm"
            free_lock.write_text("(list free)", encoding="utf-8")
            compatibility_lock.write_text("(list guix nonguix)", encoding="utf-8")
            with (
                patch("release_gate.ROOT", root),
                patch("release_gate.run", return_value=(0, "structural policy passed")) as run_mock,
            ):
                result = check_channels()

        self.assertEqual(result["status"], "pass")
        calls = [call.args[0] for call in run_mock.call_args_list]
        locks = {
            args[args.index("--policy") + 1]: Path(args[args.index("--lock") + 1]).name
            for args in calls
        }
        self.assertEqual(locks, {
            "free": "channels.lock.scm",
            "compatibility": "channels.compatibility.lock.scm",
        })


class ImageTests(unittest.TestCase):
    @staticmethod
    def nested_payload(overall: str) -> dict:
        statuses = {
            "pass": "pass",
            "fail": "fail",
            "incomplete": "not-run",
        }
        status = statuses[overall]
        return {
            "schema": "wsm-release-verdict/1",
            "artifact": "wsm.iso",
            "overall": overall,
            "criteria": [
                {"id": identifier, "status": status, "detail": f"{identifier} {status}"}
                for identifier in (
                    "checksum",
                    "manifest",
                    "iso-structure",
                    "boot-bios",
                    "boot-uefi",
                )
            ],
        }

    def run_nested(self, payload: dict, returncode: int):
        completed = subprocess.CompletedProcess(
            args=["verify_live_release.py"],
            returncode=returncode,
            stdout=json.dumps(payload),
            stderr="",
        )
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "wsm.iso"
            iso.write_bytes(b"fixture")
            with patch("release_gate.subprocess.run", return_value=completed):
                return check_image(iso, boot=True)

    def test_nested_incomplete_with_exit_zero_is_not_a_pass(self) -> None:
        result = self.run_nested(self.nested_payload("incomplete"), 0)
        self.assertEqual(result["status"], "not-run")
        self.assertIn("boot-bios", result["detail"])

    def test_nested_pass_is_accepted_only_when_all_criteria_pass(self) -> None:
        result = self.run_nested(self.nested_payload("pass"), 0)
        self.assertEqual(result["status"], "pass")

    def test_nested_fail_is_preserved(self) -> None:
        result = self.run_nested(self.nested_payload("fail"), 1)
        self.assertEqual(result["status"], "fail")

    def test_malformed_nested_verdict_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "wsm.iso"
            iso.write_bytes(b"fixture")
            completed = subprocess.CompletedProcess(
                args=["verify_live_release.py"], returncode=0, stdout="{}", stderr=""
            )
            with patch("release_gate.subprocess.run", return_value=completed):
                result = check_image(iso, boot=True)
        self.assertEqual(result["status"], "fail")

    def test_unhashable_nested_status_fails_closed(self) -> None:
        payload = self.nested_payload("pass")
        payload["criteria"][0]["status"] = []
        result = self.run_nested(payload, 0)
        self.assertEqual(result["status"], "fail")
        self.assertIn("invalid status", result["detail"])

    def test_no_iso_is_recorded_as_not_run(self) -> None:
        self.assertEqual(check_image(None, boot=False)["status"], "not-run")

    def test_missing_iso_file_fails(self) -> None:
        self.assertEqual(check_image(Path("/nonexistent/image.iso"), boot=False)["status"], "fail")


class CliTests(unittest.TestCase):
    def test_incomplete_gate_has_a_distinct_nonzero_exit_code(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "release_gate.py"), "--skip-tests", "--compact"],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["schema"], "wsm-release-gate/1")
        self.assertEqual(payload["overall"], "incomplete")
        self.assertEqual(completed.returncode, 2)
        ids = {item["id"] for item in payload["criteria"]}
        self.assertIn("channels", ids)
        self.assertIn("image", ids)


if __name__ == "__main__":
    unittest.main()
