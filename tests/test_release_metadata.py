# SPDX-License-Identifier: LicenseRef-Volnist
"""Release metadata must describe the installer behavior that actually ships."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_INFO = json.loads((ROOT / "RELEASE-INFO.json").read_text(encoding="utf-8"))
RELEASE_NOTES = (ROOT / "RELEASE-NOTES.md").read_text(encoding="utf-8")
EXECUTOR_DOC = (ROOT / "docs" / "EXECUTOR.md").read_text(encoding="utf-8")
VERIFIED_ARTIFACTS = (ROOT / "docs" / "VERIFIED-ARTIFACTS.md").read_text(encoding="utf-8")


class ReleaseMetadataContractTests(unittest.TestCase):
    def test_source_archive_name_matches_release_version(self) -> None:
        version = RELEASE_INFO["version"]
        expected_archive = f"wsm-desktop-{version}-source.tar.gz"

        self.assertEqual(version, "0.1.0-rc4")
        self.assertIn(expected_archive, RELEASE_INFO["artifacts"])
        self.assertIn(f"`{version}`", RELEASE_NOTES)
        self.assertIn("WSM Desktop RC4", RELEASE_NOTES.splitlines()[0])

    def test_every_installer_entrypoint_is_described_as_preview_only(self) -> None:
        scope = "\n".join(RELEASE_INFO["scope"])

        self.assertIn("preview contract", scope)
        self.assertIn("APPLY is disabled", scope)
        self.assertIn("not-run", scope)
        self.assertIn("no installation command is launched", scope)
        self.assertIn("APPLY вимкнено", RELEASE_NOTES)
        self.assertIn("`not-run`", RELEASE_NOTES)
        self.assertIn("preview-only", EXECUTOR_DOC)
        self.assertIn("not-run", EXECUTOR_DOC)

    def test_allowlist_is_not_described_as_execution_permission(self) -> None:
        combined = RELEASE_NOTES.lower()

        self.assertIn("це не дозвіл на їх запуск", combined)
        self.assertIn("не запускає", combined)
        self.assertNotIn("root executes only an allowlisted set of commands", combined)
        self.assertNotIn("лише тоді виконує", combined)

    def test_preview_steps_are_not_mislabeled_as_success(self) -> None:
        self.assertIn("not-run", EXECUTOR_DOC)
        self.assertIn("not-run", RELEASE_NOTES)
        self.assertIn("не `pass`", RELEASE_NOTES)
        self.assertIn("APPLY is disabled", RELEASE_INFO["scope"][2])

    def test_compatibility_pin_is_not_mislabeled_as_authentication(self) -> None:
        scope = "\n".join(RELEASE_INFO["scope"]).lower()
        notes = RELEASE_NOTES.lower()

        self.assertIn("structural check alone is not cryptographic authentication", scope)
        self.assertIn("не доводять криптографічної автентифікації", notes)
        self.assertNotIn("authenticated compatibility lock", scope)

    def test_source_recipes_are_not_claimed_as_a_verified_installed_system(self) -> None:
        excluded = "\n".join(RELEASE_INFO["excluded"]).lower()

        self.assertIn("no installation has completed", excluded)
        self.assertIn("verified bootable iso", excluded)
        self.assertIn("не доводить, що відповідний образ зібрано", RELEASE_NOTES)
        self.assertIn("не є доказом повного wsm installer boot/install", RELEASE_NOTES.lower())


    def test_previous_iso_artifact_evidence_is_scoped_and_does_not_claim_boot(self) -> None:
        notes = RELEASE_NOTES.lower()
        evidence = VERIFIED_ARTIFACTS.lower()

        self.assertIn("[реєстрі перевірених артефактів](docs/verified-artifacts.md)", notes)
        self.assertIn("wsm-desktop-kde-hardened-20261125.iso", notes)
        self.assertIn("d1a000f8c465b496565b0f611ae6f65095086a8457c663f212ca5b17073fd7ef", evidence)
        self.assertIn("wsm_live_ready", evidence)
        self.assertIn("завантаження в bios", evidence)
        self.assertIn("завантаження в uefi", evidence)
        self.assertIn("не перевірено", evidence)
        self.assertIn("інсталятор у образі не запускався", evidence)

    def test_release_notes_do_not_claim_rc4_artifact_is_published(self) -> None:
        self.assertIn("не створює й не публікує rc4", RELEASE_NOTES.lower())
        self.assertIn("have not been built or published", RELEASE_INFO["excluded"][-1])


if __name__ == "__main__":
    unittest.main()
