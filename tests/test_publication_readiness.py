# SPDX-License-Identifier: LicenseRef-Volnist
"""Publication checks real metadata and keeps scoped owner waivers visible.

The license mismatch is resolved with LicenseRef-Volnist. An unsigned Git
channel and nonfree Compatibility payload are separate from the signed Free
binary-cache lane; owner waivers must be reported, never silently erased.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_publication_readiness", ROOT / "scripts" / "check_publication_readiness.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = load_checker()

PACKAGE_OK = """\
;; SPDX-License-Identifier: LicenseRef-Volnist
(define-public wsm-tools
  (package
    (name "wsm-tools")
    (version "0.1.0")
    (license license:volnist)))
"""

PACKAGE_MISMATCH = """\
;; SPDX-License-Identifier: LicenseRef-Volnist
(define-public wsm-tools
  (package
    (name "wsm-tools")
    (license gpl3+)))
"""


class PublicationReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "wsm" / "packages").mkdir(parents=True)
        (self.root / "channels").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_package(self, text: str) -> None:
        (self.root / "wsm" / "packages" / "wsm.scm").write_text(text, encoding="utf-8")

    def test_a_missing_package_is_reported(self) -> None:
        found = checker.problems(self.root)
        self.assertTrue(any("nothing to publish" in item for item in found), found)

    def test_the_licence_mismatch_is_reported(self) -> None:
        self.write_package(PACKAGE_MISMATCH)
        found = checker.problems(self.root)
        self.assertTrue(any("#367" in item for item in found), found)

    def test_an_unsigned_channel_is_reported(self) -> None:
        self.write_package(PACKAGE_OK)
        found = checker.problems(self.root)
        self.assertTrue(any("no .guix-authorizations" in item for item in found), found)

    def test_every_package_definition_is_checked(self) -> None:
        """#367 covers three files, not just the channel package."""
        self.write_package(PACKAGE_OK)
        (self.root / ".guix-authorizations").write_text("(authorizations)\n", encoding="utf-8")
        (self.root / "systems").mkdir()
        (self.root / "systems" / "live-iso.scm").write_text(
            "(package (license license:gpl3+))\n", encoding="utf-8"
        )
        found = checker.problems(self.root)
        self.assertTrue(any("systems/live-iso.scm" in item for item in found), found)

    def test_the_gpu_model_name_is_not_a_firmware_reference(self) -> None:
        """A kernel named after the GPU is not a nonfree source."""
        self.write_package(PACKAGE_OK)
        (self.root / ".guix-authorizations").write_text("(authorizations)\n", encoding="utf-8")
        (self.root / "systems").mkdir()
        (self.root / "systems" / "compatibility.scm").write_text(
            '(define wsm-linux-gp107\n  (kernel #:name "linux-wsm-gp107"))\n', encoding="utf-8"
        )
        self.assertEqual(checker.problems(self.root), [])

    def test_firmware_in_the_free_channel_is_reported(self) -> None:
        self.write_package(PACKAGE_OK)
        (self.root / ".guix-authorizations").write_text("(authorizations)\n", encoding="utf-8")
        (self.root / "channels" / "free.scm").write_text(
            "(use-modules (gnu packages nvidia-firmware))\n", encoding="utf-8"
        )
        found = checker.problems(self.root)
        self.assertTrue(any("#586" in item for item in found), found)

    def test_an_owner_waiver_is_reported_not_hidden(self) -> None:
        """A waiver records who decided; it must not look like a pass."""
        self.write_package(PACKAGE_OK)
        (self.root / "systems").mkdir()
        (self.root / "systems" / "compatibility.scm").write_text(
            "(use-modules (nongnu packages linux))\n", encoding="utf-8"
        )
        (self.root / "etc").mkdir()
        (self.root / "etc" / "publication-waivers.scm").write_text(
            '(list (waiver (blocker "firmware-586") (owner "Власник") '
            '(date "2026-11-28") (decision "беру на себе") (scope "H170")))',
            encoding="utf-8",
        )
        self.assertIn("firmware-586", checker.read_waivers(self.root))
        # The blocker is still produced; the report decides how to present it.
        self.assertTrue(any("[firmware-586]" in item for item in checker.problems(self.root)))

    def test_an_incomplete_waiver_is_ignored(self) -> None:
        """No owner or no date is an intention, not a decision."""
        (self.root / "etc").mkdir()
        (self.root / "etc" / "publication-waivers.scm").write_text(
            '(list (waiver (blocker "firmware-586") (decision "хочу")))', encoding="utf-8"
        )
        self.assertEqual(checker.read_waivers(self.root), {})

    def test_a_clean_tree_has_no_blockers(self) -> None:
        self.write_package(PACKAGE_OK)
        (self.root / ".guix-authorizations").write_text("(authorizations)\n", encoding="utf-8")
        (self.root / "channels" / "free.scm").write_text(
            "(use-modules (guix channels))\n%default-channels\n", encoding="utf-8"
        )
        self.assertEqual(checker.problems(self.root), [])

    def test_real_repository_license_is_consistent_and_scoped_findings_are_waived(self) -> None:
        found = checker.problems(ROOT)
        self.assertFalse(any("#367" in item for item in found), found)
        waivers = checker.read_waivers(ROOT)
        self.assertIn("firmware-586", waivers)
        self.assertIn("channel-unsigned", waivers)
        unwaived = []
        for item in found:
            identifier = item[1 : item.index("]")] if item.startswith("[") else ""
            if not identifier or identifier not in waivers:
                unwaived.append(item)
        self.assertEqual(unwaived, [], f"unwaived publication findings: {unwaived}")


if __name__ == "__main__":
    unittest.main()
