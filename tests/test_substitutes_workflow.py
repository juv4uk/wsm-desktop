# SPDX-License-Identifier: LicenseRef-Volnist
"""The substitute workflow must fail loudly without a key, and never leak one."""

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
        self.steps = self.data["jobs"]["publish"]["steps"]

    def step(self, needle: str) -> dict:
        for step in self.steps:
            if needle in (step.get("name") or "") or needle in str(step.get("uses", "")):
                return step
        raise AssertionError(f"no step matching {needle!r}")

    def test_the_workflow_parses(self) -> None:
        self.assertIn("publish", self.data["jobs"])

    def test_it_runs_on_manual_dispatch(self) -> None:
        self.assertIn("workflow_dispatch", self.data[True])

    def test_it_never_runs_automatically_on_push(self) -> None:
        self.assertNotIn("push", self.data[True])

    def test_publication_is_double_gated_by_owner(self) -> None:
        dispatch = self.data[True]["workflow_dispatch"]
        publish_input = dispatch["inputs"]["publish"]
        self.assertIs(publish_input["required"], True)
        self.assertIs(publish_input["default"], False)
        publish = self.data["jobs"]["publish"]
        self.assertEqual(
            publish["if"],
            "${{ inputs.publish == true && vars.WSM_SUBSTITUTES_PUBLISH_APPROVED == 'true' }}",
        )
        self.assertIn("WSM_SUBSTITUTES_PUBLISH_APPROVED", self.data["jobs"]["publication-gate"]["if"])

    def test_write_permissions_exist_only_inside_the_approved_publish_job(self) -> None:
        self.assertEqual(self.data["permissions"]["contents"], "read")
        permissions = self.data["jobs"]["publish"]["permissions"]
        self.assertEqual(permissions, {"contents": "write", "pages": "write", "id-token": "write"})

    def test_the_key_comes_from_a_secret_and_is_checked(self) -> None:
        step = self.step("ключ")
        self.assertIn("secrets.GUIX_SIGNING_KEY", str(step))
        # Missing key must stop the run: an unsigned cache cannot be authorised
        # by a client, so publishing it would be busywork.
        self.assertIn("exit 1", step["run"])

    def test_no_key_material_is_committed(self) -> None:
        """A path is fine; the key itself is not."""
        for marker in (
            "BEGIN OPENSSH PRIVATE KEY",
            "(signing-key",
            "(private-key",
        ):
            self.assertNotIn(marker, self.text)
        # A base64 blob longer than 64 characters in a workflow is key material.
        import re

        blobs = re.findall(r"[A-Za-z0-9+/]{64,}={0,2}", self.text)
        self.assertEqual(blobs, [], f"possible key material: {blobs[:1]}")

    def test_the_cache_is_warmed_before_publishing(self) -> None:
        """`guix publish` is lazy; without a warmup the cache directory is empty."""
        warm = self.step("Прогріти")
        self.assertIn("narinfo", warm["run"])

    def test_archives_go_to_a_release_and_metadata_to_pages(self) -> None:
        self.assertIn("gh release upload substitutes", self.text)
        self.assertIn("upload-pages-artifact", self.text)
        # The split is the whole point: nar archives must not be in the site.
        self.assertIn("--base-url \"https://github.com/${{ github.repository }}/releases/download/substitutes\"", self.text)

    def test_pages_deployment_uses_the_official_actions(self) -> None:
        uses = [step.get("uses", "") for step in self.steps]
        self.assertIn("actions/upload-pages-artifact@v3", uses)
        self.assertIn("actions/deploy-pages@v4", uses)


if __name__ == "__main__":
    unittest.main()
