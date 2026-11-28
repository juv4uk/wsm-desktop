# SPDX-License-Identifier: LicenseRef-Volnist
"""Keep the first H170 Free package-evidence lane narrow and non-publishing."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ci" / "packages" / "h170-free-core.scm"
WORKFLOW = ROOT / ".github" / "workflows" / "h170-free-core-build-evidence.yml"


def manifest_roots(source: str) -> tuple[str, ...]:
    match = re.search(
        r"specifications->manifest\s*'\((.*?)\)\s*\)",
        source,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("manifest must return a specifications->manifest")
    return tuple(re.findall(r'"([a-z0-9.+-]+)"', match.group(1)))


class H170FreePackageEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = MANIFEST.read_text(encoding="utf-8")
        self.workflow_text = WORKFLOW.read_text(encoding="utf-8")
        self.workflow = yaml.load(self.workflow_text, Loader=yaml.BaseLoader)

    def test_manifest_is_exactly_the_owner_approved_first_upstream_slice(self) -> None:
        self.assertEqual(manifest_roots(self.manifest), ("linux-libre", "mesa"))

    def test_manifest_records_hardware_and_known_kernel_limit(self) -> None:
        self.assertIn("H170 Free", self.manifest)
        self.assertIn("10de:1c82", (ROOT / "drivers" / "profiles" / "h170-free.json").read_text(encoding="utf-8"))
        self.assertIn("ed7fb901fce31588bd12ab95adc36ebcb51bc8ea", self.manifest)
        self.assertIn("#514", self.manifest)

    def test_workflow_is_manual_only_and_guarded_to_main(self) -> None:
        events = self.workflow["on"]
        self.assertEqual(set(events), {"workflow_dispatch"})
        self.assertIn('GITHUB_EVENT_NAME" != "workflow_dispatch', self.workflow_text)
        self.assertIn('GITHUB_REF" != "refs/heads/main', self.workflow_text)
        concurrency = self.workflow["concurrency"]
        self.assertEqual(concurrency["group"], "h170-free-core-package-evidence-main")
        self.assertEqual(str(concurrency["cancel-in-progress"]).lower(), "false")

    def test_workflow_uses_read_only_permissions_and_exact_official_lock(self) -> None:
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        self.assertIn("4e5195be20d9b124df8a8bb69213412236e4668e", self.workflow_text)
        self.assertIn("channels.lock.scm", self.workflow_text)
        self.assertIn("ci/packages/h170-free-core.scm", self.workflow_text)

    def test_workflow_does_not_accept_user_supplied_package_or_shell_inputs(self) -> None:
        self.assertNotIn("inputs.", self.workflow_text)
        self.assertNotIn("PACKAGES", self.workflow_text)
        self.assertNotIn("github.event.inputs", self.workflow_text)

    def test_workflow_only_evaluates_and_realizes_roots_in_ephemeral_store(self) -> None:
        self.assertIn("--dry-run --no-grafts", self.workflow_text)
        self.assertIn("--no-grafts --keep-going", self.workflow_text)
        self.assertIn("guix time-machine -C channels.lock.scm", self.workflow_text)
        self.assertIn("RUNNER_TEMP", self.workflow_text)

    def test_workflow_never_exports_or_uploads_binary_outputs(self) -> None:
        for forbidden in (
            "guix archive --export",
            "actions/upload-artifact",
            "gh release upload",
            "gh release create",
            "actions/deploy-pages",
            "guix publish",
            "signing-key.sec",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.workflow_text)

    def test_workflow_reports_realized_store_paths_without_mislabeling_them_as_nar_hashes(self) -> None:
        self.assertIn("Store path", self.workflow_text)
        self.assertIn("closure report", self.workflow_text)
        self.assertNotIn("NAR SHA-256", self.workflow_text)
        self.assertNotIn("nar hash", self.workflow_text.lower())


if __name__ == "__main__":
    unittest.main()
