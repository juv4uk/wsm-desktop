# SPDX-License-Identifier: LicenseRef-Volnist
"""The one-time RC7 release is built from default main and verified before publication."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "wsm" / "packages" / "wsm.scm"
WORKFLOW = ROOT / ".github" / "workflows" / "wsm-tools-rc7-release.yml"
EVALUATION = ROOT / "tests" / "guix" / "source-module-evaluation.scm"


class WsmToolsRc7ReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.package = PACKAGE.read_text(encoding="utf-8")
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.workflow = yaml.load(self.text, Loader=yaml.BaseLoader)
        self.job = self.workflow["jobs"]["publish"]
        self.steps = self.job["steps"]

    def step(self, name: str) -> dict:
        for item in self.steps:
            if item.get("name") == name:
                return item
        raise AssertionError(f"missing workflow step: {name}")

    def test_rc7_uses_the_minimal_interpreter_and_version_matched_site_path(self) -> None:
        self.assertIn('(version "0.1.0-rc7")', self.package)
        self.assertIn("(gnu packages python-build)", self.package)
        self.assertIn("(package-version python-minimal)", self.package)
        self.assertIn("(propagated-inputs (list python-minimal python-jsonschema))", self.package)
        self.assertNotIn("(propagated-inputs (list python python-jsonschema))", self.package)
        self.assertNotIn("(gnu packages python)\n", self.package)

    def test_rc7_embeds_the_exact_license_and_uses_the_custom_license_record(self) -> None:
        self.assertIn('(doc (string-append out "/share/doc/wsm-tools"))', self.package)
        self.assertIn('(copy-file "LICENSE" (string-append doc "/LICENSE"))', self.package)
        self.assertIn('(license (license "ВОЛЬНІСТЬ"', self.package)
        self.assertIn('"file://LICENSE"', self.package)
        self.assertIn("LicenseRef-Volnist", self.package)
        self.assertNotIn("(license gpl3+)", self.package)

    def test_the_release_is_a_single_branch_creation_trigger(self) -> None:
        self.assertEqual(self.workflow["on"]["push"]["branches"], ["publish/wsm-tools-rc7"])
        self.assertNotIn("workflow_dispatch", self.workflow["on"])
        self.assertEqual(
            self.job["if"],
            "${{ github.ref == 'refs/heads/publish/wsm-tools-rc7' && github.event.before == '0000000000000000000000000000000000000000' }}",
        )
        self.assertNotIn("packages-*", self.text)
        self.assertNotIn("tags:", self.text)

    def test_the_release_target_must_be_the_current_default_main_commit(self) -> None:
        target = self.step("Resolve and verify the default-main release target")["run"]
        self.assertIn("git fetch --no-tags origin main", target)
        self.assertIn("git rev-parse refs/remotes/origin/main", target)
        self.assertIn('test "$TRIGGER_TREE" = "$MAIN_TREE"', target)
        self.assertIn('git checkout --detach "$MAIN_SHA"', target)
        release = self.step("Create a Draft Release targeting the verified default-main commit")["run"]
        self.assertIn('--target "$MAIN_SHA"', release)
        self.assertNotIn('--target "$GITHUB_SHA"', release)

    def test_guix_uses_the_official_locked_channel_and_authenticated_mirror(self) -> None:
        self.assertIn('url."https://codeberg.org/guix/guix.git".insteadOf "https://git.guix.gnu.org/guix.git"', self.text)
        self.assertIn("guix time-machine -C channels.lock.scm", self.text)
        self.assertIn("tests/guix/source-module-evaluation.scm", self.text)
        self.assertIn("wsm-tools 0.1.0-rc7", self.text)

    def test_the_pack_contains_all_three_commands_and_runtime_license(self) -> None:
        build = self.step("Build the self-contained WSM tools pack")["run"]
        for marker in (
            "/bin/wsm-hwcheck$",
            "/bin/wsm-install$",
            "/bin/wsm-install-live$",
            "/share/doc/wsm-tools/LICENSE$",
            "wsm-tools-pack.tar.zst",
            "python-minimal",
            "LICENSE",
            "SHA256SUMS",
            "PROVENANCE.txt",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, build)

    def test_attestation_and_workflow_artifact_cover_the_same_bundle(self) -> None:
        self.assertIn("actions/attest@v4", self.text)
        artifact = self.step("Keep the exact RC7 bundle as a workflow artifact")
        self.assertIn("actions/upload-artifact@v7", artifact["uses"])
        self.assertEqual(artifact["with"]["retention-days"], "30")
        self.assertIn("archives/LICENSE", artifact["with"]["path"])
        self.assertIn("archives/SHA256SUMS", artifact["with"]["path"])

    def test_release_is_drafted_then_read_back_before_becoming_public(self) -> None:
        create = self.step("Create a Draft Release targeting the verified default-main commit")["run"]
        readback = self.step("Read back and verify the Draft Release")["run"]
        publish = self.step("Publish the verified RC7 pre-release")["run"]
        self.assertIn("--draft", create)
        self.assertIn("sha256sum -c SHA256SUMS.expected", readback)
        self.assertIn("zstd -t wsm-tools-pack.tar.zst", readback)
        self.assertIn("gh release edit", publish)
        self.assertIn("--draft=false", publish)
        names = [x.get("name") for x in self.steps]
        self.assertLess(names.index("Read back and verify the Draft Release"), names.index("Publish the verified RC7 pre-release"))

    def test_permissions_are_scoped_and_no_secret_or_workflow_write_is_requested(self) -> None:
        self.assertEqual(
            self.workflow["permissions"],
            {
                "contents": "write",
                "attestations": "write",
                "id-token": "write",
                "artifact-metadata": "write",
            },
        )
        self.assertNotIn("workflows: write", self.text)
        self.assertNotIn("secrets.", self.text)
        self.assertNotIn("PAT", self.text)
        self.assertIn("GH_TOKEN: ${{ github.token }}", self.text)

    def test_combined_guix_evaluation_keeps_the_kernel_overlay_checks(self) -> None:
        evaluation = EVALUATION.read_text(encoding="utf-8")
        for marker in ("license-uri", "LicenseRef-Volnist", "linux-libre-h170", "origin-patches", "must append exactly one patch"):
            with self.subTest(marker=marker):
                self.assertIn(marker, evaluation)


if __name__ == "__main__":
    unittest.main()
