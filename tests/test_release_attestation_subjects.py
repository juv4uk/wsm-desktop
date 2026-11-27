# SPDX-License-Identifier: LicenseRef-Volnist
"""Whole and split Minimal Live images produce exact attestation subject sets."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_release_attestation_subjects import (  # noqa: E402
    SubjectListError,
    build_subject_paths,
    write_github_outputs,
)


def make_required_assets(root: Path) -> None:
    for name in (
        "SHA256SUMS",
        "build-manifest.json",
        "release-manifest.json",
        "boot-bios.json",
        "boot-uefi.json",
    ):
        (root / name).write_text(f"{name}\n", encoding="utf-8")


class ReleaseAttestationSubjectTests(unittest.TestCase):
    def test_whole_iso_has_six_subjects_and_no_split_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_required_assets(root)
            (root / "live.iso").write_bytes(b"whole image")
            subjects = build_subject_paths(root, "live.iso")
            self.assertEqual(len(subjects), 6)
            self.assertEqual(subjects[0], (root / "live.iso").resolve())
            self.assertNotIn("ISO-CHECKSUMS.sha256", [path.name for path in subjects])

    def test_split_iso_attests_every_part_and_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_required_assets(root)
            (root / "live.iso.part000").write_bytes(b"part one")
            (root / "live.iso.part001").write_bytes(b"part two")
            (root / "ISO-CHECKSUMS.sha256").write_text("checksums\n", encoding="utf-8")
            subjects = build_subject_paths(root, "live.iso")
            names = [path.name for path in subjects]
            self.assertEqual(len(subjects), 8)
            self.assertEqual(
                names[:3],
                ["live.iso.part000", "live.iso.part001", "ISO-CHECKSUMS.sha256"],
            )

    def test_split_iso_without_sidecar_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_required_assets(root)
            (root / "live.iso.part000").write_bytes(b"part one")
            with self.assertRaisesRegex(SubjectListError, "require ISO-CHECKSUMS.sha256"):
                build_subject_paths(root, "live.iso")

    def test_whole_iso_cannot_coexist_with_parts_or_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_required_assets(root)
            (root / "live.iso").write_bytes(b"whole image")
            (root / "ISO-CHECKSUMS.sha256").write_text("unexpected", encoding="utf-8")
            with self.assertRaisesRegex(SubjectListError, "cannot coexist"):
                build_subject_paths(root, "live.iso")

    def test_missing_required_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "live.iso").write_bytes(b"whole image")
            for name in (
                "SHA256SUMS",
                "build-manifest.json",
                "release-manifest.json",
                "boot-bios.json",
            ):
                (root / name).write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(SubjectListError, "boot-uefi.json"):
                build_subject_paths(root, "live.iso")

    def test_github_outputs_match_subject_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_required_assets(root)
            (root / "live.iso").write_bytes(b"whole image")
            subjects = build_subject_paths(root, "live.iso")
            subject_file = root / "subjects.txt"
            github_output = root / "github-output.txt"
            github_output.write_text("", encoding="utf-8")
            write_github_outputs(subjects, subject_file, github_output)
            self.assertEqual(
                subject_file.read_text(encoding="utf-8").splitlines(),
                [str(path) for path in subjects],
            )
            output = github_output.read_text(encoding="utf-8")
            self.assertIn(f"subject_count={len(subjects)}", output)
            self.assertIn("paths<<WSM_ATTESTATION_SUBJECTS", output)


if __name__ == "__main__":
    unittest.main()
