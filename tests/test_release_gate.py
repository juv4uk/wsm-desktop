# SPDX-License-Identifier: LicenseRef-Volnist
"""The gate must never call a skipped check a pass."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

LIVE_VERDICT_IDS = ("checksum", "manifest", "iso-structure", "boot-bios", "boot-uefi")


def verifier_payload(overrides: dict[str, object] | None = None) -> dict:
    overrides = overrides or {}
    return {
        "schema": "wsm-release-verdict/1",
        "artifact": "live.iso",
        "artifact_sha256": hashlib.sha256(b"placeholder").hexdigest(),
        "overall": "incomplete" if "not-run" in overrides.values()
        else "fail" if "fail" in overrides.values() else "pass",
        "criteria": [
            {"id": identifier, "status": overrides.get(identifier, "pass"), "detail": ""}
            for identifier in LIVE_VERDICT_IDS
        ],
    }

sys.path.insert(0, str(ROOT / "scripts"))

from release_gate import check_channels, check_image, check_tests, criterion, from_exit, verdict  # noqa: E402


class VerdictTests(unittest.TestCase):
    def test_all_pass_is_a_pass(self) -> None:
        self.assertEqual(verdict([criterion("a", "pass", "")], "free")["overall"], "pass")

    def test_any_failure_fails(self) -> None:
        self.assertEqual(
            verdict([criterion("a", "pass", ""), criterion("b", "fail", "")], "free")["overall"],
            "fail",
        )

    def test_a_skipped_check_makes_it_incomplete(self) -> None:
        """This is the whole point: silence is not success."""
        result = verdict([criterion("a", "pass", ""), criterion("b", "not-run", "no qemu")], "free")
        self.assertEqual(result["overall"], "incomplete")

    def test_failure_outranks_incomplete(self) -> None:
        result = verdict([criterion("a", "not-run", ""), criterion("b", "fail", "")], "free")
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


class TestRunnerTests(unittest.TestCase):
    def test_tests_use_one_bounded_unittest_discovery_process(self) -> None:
        with patch("release_gate.run", return_value=(0, "OK")) as run_check:
            result = check_tests()
        self.assertEqual(result["status"], "pass")
        self.assertIn("test modules", result["detail"])
        command = run_check.call_args.args[0]
        self.assertEqual(command[1:4], ["-m", "unittest", "discover"])
        self.assertEqual(run_check.call_args.kwargs["timeout"], 900)


class ChannelTests(unittest.TestCase):
    def _locks(self, root: Path):
        free_lock = root / "channels.lock.scm"
        compatibility_lock = root / "channels" / "compatibility.lock.scm"
        return {"free": free_lock, "compatibility": compatibility_lock}

    def test_free_product_passes_without_claiming_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            locks = self._locks(root)
            locks["free"].write_text("(list)", encoding="utf-8")
            with patch("release_gate.CHANNEL_LOCKS", new=locks), patch(
                "release_gate.run", return_value=(0, "Free structural policy passed")
            ) as run_check:
                result = check_channels("free")
        self.assertEqual(result["status"], "pass")
        self.assertIn("free product", result["detail"])
        self.assertEqual(run_check.call_count, 2)
        command = run_check.call_args.args[0]
        self.assertIn("free", command)
        self.assertEqual(Path(command[command.index("--lock") + 1]), locks["free"])

    def test_channel_authentication_missing_guix_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            locks = self._locks(Path(temporary))
            locks["free"].write_text("(list)", encoding="utf-8")
            with patch("release_gate.CHANNEL_LOCKS", new=locks), patch(
                "release_gate.run", side_effect=[(0, "structural pass"), (127, "guix missing")]
            ):
                result = check_channels("free")
        self.assertEqual(result["status"], "not-run")
        self.assertIn("free-authentication", result["detail"])

    def test_channel_authentication_failure_is_not_a_structural_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            locks = self._locks(Path(temporary))
            locks["free"].write_text("(list)", encoding="utf-8")
            with patch("release_gate.CHANNEL_LOCKS", new=locks), patch(
                "release_gate.run", side_effect=[(0, "structural pass"), (1, "signature verification failed")]
            ):
                result = check_channels("free")
        self.assertEqual(result["status"], "fail")
        self.assertIn("signature verification failed", result["detail"])

    def test_compatibility_product_missing_lock_is_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            locks = self._locks(Path(temporary))
            with patch("release_gate.CHANNEL_LOCKS", new=locks), patch(
                "release_gate.run"
            ) as run_check:
                result = check_channels("compatibility")
        self.assertEqual(result["status"], "not-run")
        self.assertIn("Compatibility lock NOT_CONFIGURED", result["detail"])
        run_check.assert_not_called()

    def test_compatibility_product_uses_only_its_own_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            locks = self._locks(Path(temporary))
            locks["compatibility"].parent.mkdir(parents=True, exist_ok=True)
            locks["compatibility"].write_text("(list)", encoding="utf-8")
            with patch("release_gate.CHANNEL_LOCKS", new=locks), patch(
                "release_gate.run", return_value=(0, "Compatibility structural policy passed")
            ) as run_check:
                result = check_channels("compatibility")
        self.assertEqual(result["status"], "pass")
        run_check.assert_called_once()
        command = run_check.call_args.args[0]
        self.assertIn("compatibility", command)
        self.assertEqual(Path(command[command.index("--lock") + 1]), locks["compatibility"])

    def test_all_products_is_incomplete_when_compatibility_is_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            locks = self._locks(Path(temporary))
            locks["free"].write_text("(list)", encoding="utf-8")
            with patch("release_gate.CHANNEL_LOCKS", new=locks), patch(
                "release_gate.run", return_value=(0, "Free structural policy passed")
            ):
                result = check_channels("all")
        self.assertEqual(result["status"], "not-run")
        self.assertIn("Compatibility lock NOT_CONFIGURED", result["detail"])

    def test_all_products_requires_both_configured_locks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            locks = self._locks(Path(temporary))
            locks["free"].write_text("(list)", encoding="utf-8")
            locks["compatibility"].write_text("(list)", encoding="utf-8")
            with patch("release_gate.CHANNEL_LOCKS", new=locks), patch(
                "release_gate.run",
                side_effect=[(0, "Free pass"), (0, "Compatibility pass")],
            ) as run_check:
                result = check_channels("all")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(run_check.call_count, 2)

    def test_missing_required_free_lock_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            locks = self._locks(Path(temporary))
            with patch("release_gate.CHANNEL_LOCKS", new=locks), patch(
                "release_gate.run"
            ) as run_check:
                result = check_channels("free")
        self.assertEqual(result["status"], "fail")
        self.assertIn("required Free lock is missing", result["detail"])
        run_check.assert_not_called()



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

    def test_verifier_wrong_iso_sha256_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "live.iso"
            iso.write_bytes(b"selected ISO bytes differ")
            payload = verifier_payload()
            completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(payload), stderr=""
            )
            with patch("release_gate.subprocess.run", return_value=completed):
                result = check_image(iso, boot=False)
        self.assertEqual(result["status"], "fail")
        self.assertIn("SHA-256 does not match", result["detail"])
    def test_verifier_wrong_iso_artifact_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "live.iso"
            iso.write_bytes(b"placeholder")
            payload = verifier_payload()
            payload["artifact"] = "other.iso"
            completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(payload), stderr=""
            )
            with patch("release_gate.subprocess.run", return_value=completed):
                result = check_image(iso, boot=False)
        self.assertEqual(result["status"], "fail")
        self.assertIn("different ISO artifact", result["detail"])

    def test_verifier_rejects_non_string_status_without_raising(self) -> None:
        for malformed in ([], {}):
            with self.subTest(malformed=malformed), tempfile.TemporaryDirectory() as temporary:
                iso = Path(temporary) / "live.iso"
                iso.write_bytes(b"placeholder")
                payload = verifier_payload({"checksum": malformed})
                completed = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=json.dumps(payload), stderr=""
                )
                with patch("release_gate.subprocess.run", return_value=completed):
                    result = check_image(iso, boot=False)
            self.assertEqual(result["status"], "fail")
            self.assertIn("malformed criteria", result["detail"])

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
    def test_release_gate_make_target_defaults_to_free(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("PRODUCT ?= free", makefile)
        self.assertIn('scripts/release_gate.py --product "$(PRODUCT)"', makefile)
        self.assertIn('$(if $(ISO),--iso "$(ISO)")', makefile)

    def test_product_selection_is_required(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "release_gate.py"), "--skip-tests", "--compact"],
            capture_output=True, text=True, check=False, cwd=ROOT,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--product", completed.stderr)

    def test_gate_emits_a_verdict_and_exits_incomplete_when_checks_are_missing(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "release_gate.py"), "--product", "free", "--skip-tests", "--compact"],
            capture_output=True, text=True, check=False, cwd=ROOT,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["schema"], "wsm-release-gate/1")
        self.assertEqual(payload["product"], "free")
        # An incomplete verdict must be non-zero so shell/CI cannot mistake it for a pass.
        self.assertEqual(payload["overall"], "incomplete")
        self.assertEqual(completed.returncode, 2)
        ids = {item["id"] for item in payload["criteria"]}
        self.assertIn("channels", ids)
        self.assertIn("image", ids)


if __name__ == "__main__":
    unittest.main()
