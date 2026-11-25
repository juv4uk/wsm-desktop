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

LIVE_VERDICT_IDS = ("checksum", "manifest", "iso-structure", "boot-bios", "boot-uefi")


def verifier_payload(overrides: dict[str, str] | None = None) -> dict:
    overrides = overrides or {}
    return {
        "schema": "wsm-release-verdict/1",
        "overall": "incomplete" if "not-run" in overrides.values()
        else "fail" if "fail" in overrides.values() else "pass",
        "criteria": [
            {"id": identifier, "status": overrides.get(identifier, "pass"), "detail": ""}
            for identifier in LIVE_VERDICT_IDS
        ],
    }

sys.path.insert(0, str(ROOT / "scripts"))

from release_gate import check_channels, check_image, criterion, from_exit, verdict  # noqa: E402


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
    def test_missing_tool_is_not_run_not_fail(self) -> None:
        self.assertEqual(from_exit("x", 127, "guix not found")["status"], "not-run")

    def test_zero_is_pass(self) -> None:
        self.assertEqual(from_exit("x", 0, "")["status"], "pass")

    def test_nonzero_is_fail(self) -> None:
        self.assertEqual(from_exit("x", 1, "")["status"], "fail")

    def test_timeout_is_fail_not_missing_tool(self) -> None:
        self.assertEqual(from_exit("x", 124, "timed out")["status"], "fail")


class ChannelTests(unittest.TestCase):
    def test_missing_compatibility_lock_is_not_run_when_free_lock_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            free_lock = root / "channels.lock.scm"
            compatibility_lock = root / "channels.compatibility.lock.scm"
            free_lock.write_text("(list)", encoding="utf-8")
            with patch(
                "release_gate.CHANNEL_LOCKS",
                new={ "free": free_lock, "compatibility": compatibility_lock },
            ), patch("release_gate.run", return_value=(0, "Free structural policy passed")) as run_check:
                result = check_channels()
        self.assertEqual(result["status"], "not-run")
        self.assertIn("Compatibility lock NOT_CONFIGURED", result["detail"])
        self.assertEqual(run_check.call_count, 1)
        self.assertIn("free", run_check.call_args.args[0])

    def test_missing_free_lock_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            free_lock = root / "channels.lock.scm"
            compatibility_lock = root / "channels.compatibility.lock.scm"
            with patch(
                "release_gate.CHANNEL_LOCKS",
                new={"free": free_lock, "compatibility": compatibility_lock},
            ), patch("release_gate.run") as run_check:
                result = check_channels()
        self.assertEqual(result["status"], "fail")
        self.assertIn("required Free lock is missing", result["detail"])
        run_check.assert_not_called()

    def test_both_configured_locks_must_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            free_lock = root / "channels.lock.scm"
            compatibility_lock = root / "channels.compatibility.lock.scm"
            free_lock.write_text("(list)", encoding="utf-8")
            compatibility_lock.write_text("(list)", encoding="utf-8")
            with patch(
                "release_gate.CHANNEL_LOCKS",
                new={"free": free_lock, "compatibility": compatibility_lock},
            ), patch(
                "release_gate.run",
                side_effect=[(0, "Free pass"), (0, "Compatibility pass")],
            ) as run_check:
                result = check_channels()
        self.assertEqual(result["status"], "pass")
        self.assertEqual(run_check.call_count, 2)



class ImageTests(unittest.TestCase):
    def test_no_iso_is_recorded_as_not_run(self) -> None:
        result = check_image(None, boot=False)
        self.assertEqual(result["status"], "not-run")

    def test_missing_iso_file_fails(self) -> None:
        result = check_image(Path("/nonexistent/image.iso"), boot=False)
        self.assertEqual(result["status"], "fail")

    def test_verifier_incomplete_result_is_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "live.iso"
            iso.write_bytes(b"placeholder")
            payload = verifier_payload({"boot-bios": "not-run"})
            payload["criteria"][3]["detail"] = "QEMU unavailable"
            completed = subprocess.CompletedProcess(
                args=[], returncode=2, stdout=json.dumps(payload), stderr=""
            )
            with patch("release_gate.subprocess.run", return_value=completed):
                result = check_image(iso, boot=True)
        self.assertEqual(result["status"], "not-run")
        self.assertIn("QEMU unavailable", result["detail"])

    def test_verifier_full_pass_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "live.iso"
            iso.write_bytes(b"placeholder")
            payload = verifier_payload()
            completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(payload), stderr=""
            )
            with patch("release_gate.subprocess.run", return_value=completed):
                result = check_image(iso, boot=False)
        self.assertEqual(result["status"], "pass")


    def test_verifier_empty_criteria_cannot_claim_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "live.iso"
            iso.write_bytes(b"placeholder")
            payload = {"schema": "wsm-release-verdict/1", "overall": "pass", "criteria": []}
            completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(payload), stderr=""
            )
            with patch("release_gate.subprocess.run", return_value=completed):
                result = check_image(iso, boot=False)
        self.assertEqual(result["status"], "fail")
        self.assertIn("no criteria", result["detail"])

    def test_verifier_duplicate_or_missing_criteria_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "live.iso"
            iso.write_bytes(b"placeholder")
            payload = verifier_payload()
            payload["criteria"].pop()
            completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(payload), stderr=""
            )
            with patch("release_gate.subprocess.run", return_value=completed):
                result = check_image(iso, boot=False)
        self.assertEqual(result["status"], "fail")
        self.assertIn("required set", result["detail"])

    def test_verifier_failure_remains_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "live.iso"
            iso.write_bytes(b"placeholder")
            payload = verifier_payload({"iso-structure": "fail"})
            payload["criteria"][2]["detail"] = "bad PVD"
            completed = subprocess.CompletedProcess(
                args=[], returncode=1, stdout=json.dumps(payload), stderr=""
            )
            with patch("release_gate.subprocess.run", return_value=completed):
                result = check_image(iso, boot=False)
        self.assertEqual(result["status"], "fail")
        self.assertIn("bad PVD", result["detail"])


class CliTests(unittest.TestCase):
    def test_gate_emits_a_verdict_and_exits_incomplete_when_checks_are_missing(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "release_gate.py"), "--skip-tests", "--compact"],
            capture_output=True, text=True, check=False, cwd=ROOT,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["schema"], "wsm-release-gate/1")
        # An incomplete verdict must be non-zero so shell/CI cannot mistake it for a pass.
        self.assertEqual(payload["overall"], "incomplete")
        self.assertEqual(completed.returncode, 2)
        ids = {item["id"] for item in payload["criteria"]}
        self.assertIn("channels", ids)
        self.assertIn("image", ids)


if __name__ == "__main__":
    unittest.main()
