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

    def test_pinned_guix_checkout_cache_uses_the_lock_files(self) -> None:
        step = self.step("Restore or save the pinned Guix checkout cache")
        self.assertEqual(step["uses"], "actions/cache@v4")
        self.assertEqual(step["with"]["path"], "~/.cache/guix/checkouts")
        self.assertIn("hashFiles('channels.lock.scm', 'channels/*.scm')", step["with"]["key"])
        self.assertEqual(step["with"]["restore-keys"], "guix-checkouts-")

    def test_no_arbitrary_package_shell_input_exists(self) -> None:
        self.assertNotIn("inputs:", self.text)
        self.assertNotIn("github.event.inputs", self.text)
        self.assertNotIn("PACKAGES=", self.text)

    def test_guix_fetch_uses_the_project_mirror_without_disabling_authentication(self) -> None:
        step = self.step("Use the GNU Guix project's authenticated Codeberg mirror")
        self.assertEqual(step["uses"], None)
        self.assertIn("https://codeberg.org/guix/guix.git", step["run"])
        self.assertIn("git.guix.gnu.org/guix.git", step["run"])
        self.assertIn("channels.lock.scm", self.text)
        self.assertNotIn("--disable-authentication", self.text)

    def test_build_uses_the_exact_locked_manifest(self) -> None:
        build = self.step("Evaluate and build the fixed H170 Free manifest")["run"]
        self.assertIn("guix time-machine -C channels.lock.scm", build)
        self.assertIn("--manifest=drivers/profiles/h170-free-packages.scm", build)
        self.assertIn("--dry-run", build)
        self.assertIn("--no-grafts", build)
        self.assertIn('-lt 11', build)
        self.assertIn("11 manifest roots", build)
        bake = self.step("Bake signed NARs into the local substitute cache")["run"]
        self.assertIn("EXPECTED_STORE_PATH_COUNT", bake)
        self.assertIn('-eq "$EXPECTED_STORE_PATH_COUNT"', bake)
        prepare = self.step("Prepare immutable Release assets and Pages metadata")["run"]
        self.assertIn("EXPECTED_STORE_PATH_COUNT", prepare)

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

    def test_signing_key_is_ephemeral_and_private_material_never_leaves_runner(self) -> None:
        step = self.step("Create an ephemeral Guix signing key for this cache run")
        self.assertIn("sudo guix archive --generate-key", step["run"])
        self.assertIn("/etc/guix/signing-key.sec", step["run"])
        self.assertIn("/etc/guix/signing-key.pub", step["run"])
        self.assertIn("ephemeral runner", step["run"])
        self.assertNotIn("WSM_SUBSTITUTES_SIGNED=false", self.text)
        self.assertNotIn("GUIX_SIGNING_KEY", self.text)
        self.assertNotIn("secrets.GUIX_SIGNING_KEY", self.text)
        self.assertNotIn("vars.GUIX_SIGNING_PUBLIC_KEY", self.text)
        self.assertNotIn("signing-key.sec", self.text.split("gh release upload", 1)[-1])
        self.assertEqual(self.data["permissions"]["attestations"], "write")
        self.assertEqual(self.data["permissions"]["artifact-metadata"], "write")

    def test_latest_cache_run_supersedes_stale_work_and_retries_get_unique_tags(self) -> None:
        self.assertIn("cancel-in-progress: true", self.text)
        self.assertIn('CACHE_TAG="h170-free-cache-${GITHUB_RUN_ID}-attempt-${GITHUB_RUN_ATTEMPT}"', self.text)
    def test_public_key_and_provenance_are_published_and_attested(self) -> None:
        prepare = self.step("Prepare immutable Release assets and Pages metadata")["run"]
        self.assertIn("./site/signing-key.pub", prepare)
        self.assertIn("./site/provenance.json", prepare)
        self.assertIn("./site/SHA256SUMS", prepare)
        self.assertIn("private_key_published", prepare)
        self.assertIn("ephemeral-per-run", prepare)
        self.assertIn("./site/signing-key.pub", self.text)
        self.assertIn("actions/attest@v4", self.text)
        self.assertIn("subject-path:", self.text)

    def test_guix_publish_uses_the_explicit_key_pair_and_cache(self) -> None:
        step = self.step("Bake signed NARs into the local substitute cache")["run"]
        self.assertIn("--cache=", step)
        self.assertIn("--compression=zstd:9", step)
        self.assertIn("--public-key=/etc/guix/signing-key.pub", step)
        self.assertIn("--private-key=/etc/guix/signing-key.sec", step)
        self.assertIn("narinfo_url", step)
        self.assertIn("sed -n 's/^URL: //p'", step)
        self.assertIn('case "$nar_url" in', step)
        self.assertIn("nar/*)", step)
        self.assertIn('curl -fsS "http://127.0.0.1:3000/$nar_url"', step)
        self.assertIn("baked", step)

    def test_release_assets_and_pages_are_both_deployed(self) -> None:
        self.assertIn("gh release create", self.text)
        self.assertIn("gh release upload", self.text)
        self.assertIn("actions/upload-pages-artifact@v3", self.text)
        self.assertIn("actions/deploy-pages@v4", self.text)
        self.assertIn("h170-free-cache-", self.text)
        self.assertIn("signing-key.pub", self.text)
        self.assertIn("SHA256SUMS", self.text)
        self.assertIn("provenance.json", self.text)

    def test_release_stays_draft_until_attestation_and_readback_pass(self) -> None:
        create = self.text.index("gh release create")
        upload = self.text.index("gh release upload")
        attest = self.text.index("uses: actions/attest@v4")
        readback = self.text.index("Read back and verify the draft Release assets")
        publish = self.text.index("Publish the verified H170 Free Release")
        pages = self.text.index("Deploy Pages metadata")
        self.assertLess(create, upload)
        self.assertLess(upload, attest)
        self.assertLess(attest, readback)
        self.assertLess(readback, publish)
        self.assertLess(publish, pages)
        self.assertIn("--draft", self.text[create:attest])
        self.assertIn("gh release download", self.text[readback:publish])
        self.assertIn("sha256sum -c SHA256SUMS", self.text[readback:publish])
        self.assertIn("sha256sum -c metadata.SHA256SUMS", self.text[readback:publish])
        self.assertIn("zstd -t", self.text[readback:publish])
        self.assertIn("draft=false", self.text[publish:pages])

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
