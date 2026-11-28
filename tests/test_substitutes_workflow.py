# SPDX-License-Identifier: LicenseRef-Volnist
"""H170 Free substitutes use an ephemeral signing key and immutable outputs."""

from __future__ import annotations

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
        for item in self.steps:
            if needle in (item.get("name") or ""):
                return item
        raise AssertionError(f"workflow step not found: {needle}")

    def test_workflow_runs_on_main_inputs_or_manually(self) -> None:
        self.assertEqual(self.events["push"]["branches"], ["main"])
        self.assertIn("workflow_dispatch", self.events)
        self.assertEqual(self.job["if"], "${{ github.ref == 'refs/heads/main' }}")

    def test_build_uses_the_exact_lock_and_fixed_ten_package_manifest(self) -> None:
        build = self.step("Evaluate and build the fixed H170 Free manifest")["run"]
        self.assertIn("guix time-machine -C channels.lock.scm", build)
        self.assertIn("--manifest=drivers/profiles/h170-free-packages.scm", build)
        self.assertIn("--dry-run", build)
        self.assertIn("--no-grafts", build)
        self.assertIn('-ne 10', build)
        self.assertIn('test_h170_free_package_manifest.py', build)

    def test_signing_key_is_ephemeral_to_the_runner_and_not_a_repository_secret(self) -> None:
        step = self.step("Generate an ephemeral signing key")
        self.assertIn("guix archive --generate-key", step["run"])
        self.assertIn("/etc/guix/signing-key.sec", step["run"])
        self.assertIn("/etc/guix/signing-key.pub", step["run"])
        self.assertNotIn("secrets.", self.text)
        self.assertNotIn("vars.GUIX_SIGNING_PUBLIC_KEY", self.text)
        self.assertIn("private key never leaves", self.text.lower())

    def test_guix_publish_uses_the_run_key_and_bakes_all_ten_nars(self) -> None:
        step = self.step("Bake signed NARs into the local substitute cache")["run"]
        self.assertIn("--cache=", step)
        self.assertIn("--compression=zstd:9", step)
        self.assertIn("--public-key=/etc/guix/signing-key.pub", step)
        self.assertIn("--private-key=/etc/guix/signing-key.sec", step)
        self.assertIn("narinfo_url", step)
        self.assertIn('NAR_COUNT', step)
        self.assertIn('-eq 10', step)

    def test_release_and_pages_publish_key_provenance_and_narinfo(self) -> None:
        self.assertIn("gh release create", self.text)
        self.assertIn("gh release upload", self.text)
        self.assertIn("actions/upload-pages-artifact@v3", self.text)
        self.assertIn("actions/deploy-pages@v4", self.text)
        self.assertIn("signing-key.pub", self.text)
        self.assertIn("provenance.txt", self.text)
        self.assertIn("SHA256SUMS", self.text)
        self.assertIn("gh release download", self.text)
        self.assertIn("sha256sum -c SHA256SUMS", self.text)

    def test_no_private_key_is_committed_or_uploaded(self) -> None:
        for marker in ("BEGIN OPENSSH PRIVATE KEY", "(signing-key", "(private-key"):
            self.assertNotIn(marker, self.text)
        self.assertNotIn('gh release upload "$CACHE_TAG" "$OUT/signing-key.sec"', self.text)

    def test_failure_is_reported_without_claiming_success(self) -> None:
        step = self.step("Report publication failure")
        self.assertIn("failure()", str(step.get("if")))
        self.assertIn("No success is claimed", step["run"])


if __name__ == "__main__":
    unittest.main()
