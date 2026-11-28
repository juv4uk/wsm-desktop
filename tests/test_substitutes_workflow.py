# SPDX-License-Identifier: LicenseRef-Volnist
"""The H170 Free substitute workflow publishes a fixed, pinned upstream-only manifest."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "substitutes.yml"


class SubstituteWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.data = yaml.safe_load(self.text)
        self.events = self.data[True]
        self.job = self.data["jobs"]["publish"]
        self.steps = self.job["steps"]

    def step(self, needle: str) -> dict:
        for step in self.steps:
            if needle in (step.get("name") or ""):
                return step
        raise AssertionError(f"no step matching {needle!r}")

    def test_workflow_parses_and_targets_main_only(self) -> None:
        self.assertIn("publish", self.data["jobs"])
        self.assertIn("workflow_dispatch", self.events)
        self.assertEqual(self.events["push"]["branches"], ["main"])
        self.assertEqual(self.job["if"], "${{ github.ref == 'refs/heads/main' }}")

    def test_push_trigger_is_limited_to_release_inputs(self) -> None:
        paths = set(self.events["push"]["paths"])
        self.assertTrue({
            ".github/workflows/substitutes.yml",
            "channels.lock.scm",
            "drivers/profiles/h170-free-packages.scm",
            "scripts/narinfo_to_release_urls.py",
        }.issubset(paths))

    def test_no_arbitrary_package_shell_input_exists(self) -> None:
        self.assertNotIn("inputs:", self.text)
        self.assertNotIn("github.event.inputs", self.text)
        self.assertNotRegex(self.text, r"PACKAGES=.*\$\{\{")

    def test_build_uses_the_exact_locked_manifest(self) -> None:
        build = self.step("Evaluate and build the fixed H170 Free manifest")["run"]
        self.assertIn("guix time-machine -C channels.lock.scm", build)
        self.assertIn("--manifest=drivers/profiles/h170-free-packages.scm", build)
        self.assertIn("--dry-run", build)
        self.assertIn("--no-grafts", build)
        self.assertIn("-ne 11", build)

    def test_the_package_manifest_excludes_owned_and_nonfree_payloads(self) -> None:
        manifest = (ROOT / "drivers" / "profiles" / "h170-free-packages.scm").read_text(encoding="utf-8")
        for forbidden in (
            '"wsm-tools"',
            '"wsm-live-tools"',
            '"linux-firmware"',
            '"nvidia-firmware"',
            '"nonguix"',
            '"intel-microcode"',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, manifest)

    def test_signing_key_is_owner_controlled_and_pair_is_required(self) -> None:
        step = self.step("Validate owner-controlled substitute signing keys")
        self.assertIn("secrets.GUIX_SIGNING_KEY", str(step))
        self.assertIn("vars.GUIX_SIGNING_PUBLIC_KEY", str(step))
        self.assertIn("exit 1", step["run"])
        self.assertNotIn("guix archive --generate-key", step["run"])

    def test_guix_publish_uses_the_explicit_key_pair_and_cache(self) -> None:
        step = self.step("Bake signed NARs into the local substitute cache")["run"]
        self.assertIn("--cache=", step)
        self.assertIn("--compression=zstd:9", step)
        self.assertIn("--public-key=/etc/guix/signing-key.pub", step)
        self.assertIn("--private-key=/etc/guix/signing-key.sec", step)
        self.assertIn("narinfo_url", step)
        self.assertIn("baked", step)

    def test_release_assets_and_pages_are_both_deployed(self) -> None:
        self.assertIn("gh release create", self.text)
        self.assertIn("gh release upload", self.text)
        self.assertIn("actions/upload-pages-artifact@v3", self.text)
        self.assertIn("actions/deploy-pages@v4", self.text)
        self.assertIn("h170-free-cache-", self.text)

    def test_failure_is_reported_without_claiming_success(self) -> None:
        step = self.step("Report publication failure")
        self.assertIn("failure()", str(step.get("if")))
        self.assertIn("No success is claimed", step["run"])

    def test_no_private_key_or_binary_payload_is_committed(self) -> None:
        for marker in ("BEGIN OPENSSH PRIVATE KEY", "(signing-key", "(private-key"):
            self.assertNotIn(marker, self.text)
        blobs = [b for b in re.findall(r"[A-Za-z0-9+/]{64,}={0,2}", self.text)
                 if re.search(r"[g-zG-Z+/]", b)]
        self.assertEqual(blobs, [], f"possible key material: {blobs[:1]}")


if __name__ == "__main__":
    unittest.main()
