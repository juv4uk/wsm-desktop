# SPDX-License-Identifier: LicenseRef-Volnist
"""The WSM package workflows: deliberate package tags, signed cache, no private keys in Git."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "substitutes.yml"
ARCHIVE_WORKFLOW = ROOT / ".github" / "workflows" / "package-archives.yml"


class SubstituteWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.data = yaml.safe_load(self.text)
        self.job = self.data["jobs"]["publish"]
        self.steps = self.job["steps"]

    def step(self, needle: str) -> dict:
        for step in self.steps:
            if needle in (step.get("name") or ""):
                return step
        raise AssertionError(f"no step matching {needle!r}")

    def test_the_workflow_parses(self) -> None:
        self.assertIn("publish", self.data["jobs"])

    def test_publication_starts_only_by_manual_request_or_package_tag(self) -> None:
        events = self.data[True]
        self.assertIn("workflow_dispatch", events)
        self.assertEqual(events["push"]["tags"], ["packages-*"])
        self.assertNotIn("branches", events["push"])

    def test_the_job_is_not_disabled(self) -> None:
        self.assertNotEqual(self.job.get("if"), "${{ false }}")
        self.assertNotIn("if: ${{ false }}", self.text)

    def test_the_owner_decision_is_recorded(self) -> None:
        self.assertIn("2026-11-28", self.text)
        self.assertIn("ВЛАСНИК ДАВ ДОЗВІЛ", self.text)

    def test_the_key_comes_from_a_secret_and_is_checked(self) -> None:
        step = self.step("ключ")
        self.assertIn("secrets.GUIX_SIGNING_KEY", str(step))
        self.assertIn("exit 1", step["run"])

    def test_no_key_material_is_committed(self) -> None:
        for marker in ("BEGIN OPENSSH PRIVATE KEY", "(signing-key", "(private-key"):
            self.assertNotIn(marker, self.text)
        blobs = [b for b in re.findall(r"[A-Za-z0-9+/]{64,}={0,2}", self.text)
                 if re.search(r"[g-zG-Z+/]", b)]
        self.assertEqual(blobs, [], f"possible key material: {blobs[:1]}")

    def test_guix_is_installed_from_the_pinned_tarball(self) -> None:
        step = self.step("Встановити")
        self.assertIn("guix-binary-", step["run"])
        self.assertIn("sha256sum -c -", step["run"])
        self.assertNotIn("guix-install.sh", step["run"])
        code = "\\n".join(line.split("#")[0] for line in self.text.splitlines())
        self.assertNotIn("--unattended", code)

    def test_the_daemon_socket_is_waited_for(self) -> None:
        self.assertIn("daemon-socket/socket", self.step("Встановити")["run"])

    def test_the_h170_free_package_set_uses_local_wsm_and_pinned_upstream(self) -> None:
        run = self.step("Зібрати пакетний набір")["run"]
        self.assertIn("guix time-machine -C channels.lock.scm -- build --no-substitutes", run)
        self.assertIn("-L . -e '(@ (wsm packages wsm) wsm-tools)' linux-libre mesa", run)
        self.assertNotIn("guix build --no-substitutes $PACKAGES", run)

    def test_cache_warmup_fetches_the_nar_archive(self) -> None:
        run = self.step("Прогріти")["run"]
        self.assertIn(".narinfo", run)
        self.assertIn("URL:", run)
        self.assertIn("curl -fsSL", run)
        self.assertIn("nar/", run)
        self.assertIn("/var/cache/publish/nar", run)

    def test_archives_go_to_a_release_and_metadata_to_pages(self) -> None:
        self.assertIn("gh release upload substitutes", self.text)
        self.assertIn("upload-pages-artifact@v3", self.text)
        self.assertIn("releases/download/substitutes", self.text)

    def test_pages_publish_cache_info_and_public_signing_key(self) -> None:
        step = self.step("Переписати URL")
        run = step["run"]
        self.assertIn("http://localhost:3000/nix-cache-info", run)
        self.assertIn("http://localhost:3000/signing-key.pub", run)
        self.assertIn("test -s ./site/nix-cache-info", run)
        self.assertIn("test -s ./site/signing-key.pub", run)


class PackageArchiveWorkflowTests(unittest.TestCase):
    def test_package_archive_uses_same_deliberate_tag_namespace(self) -> None:
        workflow = yaml.safe_load(ARCHIVE_WORKFLOW.read_text(encoding="utf-8"))
        events = workflow[True]
        self.assertEqual(events["push"]["tags"], ["packages-*"])
        self.assertIn("workflow_dispatch", events)
        self.assertNotIn("branches", events["push"])

    def test_package_archive_resolves_wsm_tools_from_its_local_module(self) -> None:
        workflow = yaml.safe_load(ARCHIVE_WORKFLOW.read_text(encoding="utf-8"))
        steps = workflow["jobs"]["archive"]["steps"]
        build = next(step for step in steps if "Build the requested packages" in step.get("name", ""))
        run = build["run"]
        self.assertIn("guix time-machine -C channels.lock.scm", run)
        self.assertIn("-e '(@ (wsm packages wsm) wsm-tools)'", run)
        self.assertIn("inputs.packages || 'wsm-tools linux-libre mesa'", run)


if __name__ == "__main__":
    unittest.main()
