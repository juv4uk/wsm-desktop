# SPDX-License-Identifier: LicenseRef-Volnist
"""The substitute workflow: owner-approved, manual-only, key never in the repo.

History worth keeping: an earlier revision of this workflow published on every
push to main and was replaced by a disabled stub until the owner decided on key
custody and the endpoint. The owner approved publication on 2026-11-28. What
stays forbidden is what the stub was protecting: automatic publishing and key
material in the repository.
"""

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
        self.job = self.data["jobs"]["publish"]
        self.steps = self.job["steps"]

    def step(self, needle: str) -> dict:
        for step in self.steps:
            if needle in (step.get("name") or ""):
                return step
        raise AssertionError(f"no step matching {needle!r}")

    def test_the_workflow_parses(self) -> None:
        self.assertIn("publish", self.data["jobs"])

    def test_publication_is_manual_only(self) -> None:
        """Automatic publishing on every push was the stub's first objection."""
        self.assertIn("workflow_dispatch", self.data[True])
        self.assertNotIn("push", self.data[True])

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
        # Hex-only runs of 64 characters are digests, not keys; a key blob has
        # characters outside [0-9a-f].
        blobs = [b for b in re.findall(r"[A-Za-z0-9+/]{64,}={0,2}", self.text)
                 if re.search(r"[g-zG-Z+/]", b)]
        self.assertEqual(blobs, [], f"possible key material: {blobs[:1]}")

    def test_guix_is_installed_from_the_pinned_tarball(self) -> None:
        """`guix-install.sh` has no --unattended and fails on a wget network error."""
        step = self.step("Встановити")
        self.assertIn("guix-binary-", step["run"])
        self.assertIn("sha256sum -c -", step["run"])
        self.assertNotIn("guix-install.sh", step["run"])
        # The comment explains why the installer was dropped; the code must not
        # use the flag that never existed.
        code = "\n".join(line.split("#")[0] for line in self.text.splitlines())
        self.assertNotIn("--unattended", code)

    def test_the_daemon_socket_is_waited_for(self) -> None:
        """A missing socket looks like a broken installer; say so explicitly."""
        self.assertIn("daemon-socket/socket", self.step("Встановити")["run"])

    def test_the_cache_is_warmed_before_publishing(self) -> None:
        self.assertIn("narinfo", self.step("Прогріти")["run"])

    def test_archives_go_to_a_release_and_metadata_to_pages(self) -> None:
        self.assertIn("gh release upload substitutes", self.text)
        self.assertIn("upload-pages-artifact@v3", self.text)
        self.assertIn("releases/download/substitutes", self.text)


if __name__ == "__main__":
    unittest.main()
