# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the Hardware Preview release helpers."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE = ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json"


class HardwareCheckScriptTests(unittest.TestCase):
    def test_fixture_report_produces_verified_diagnostic_plans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "check"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "wsm_hardware_check.py"),
                    "--out",
                    str(output),
                    "--report",
                    str(FIXTURE),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("pass", result.stdout)

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["overall"], "pass")
            self.assertEqual(set(manifest["plans"]), {"guix", "nix"})
            for backend in ("guix", "nix"):
                plan_entry = manifest["plans"][backend]
                self.assertEqual(plan_entry["status"], "verified-diagnostic")
                self.assertTrue(plan_entry["safe_execution_flags"])
                self.assertTrue(plan_entry["plan_sha256_matches"])

            expected = {
                "report.json",
                "plan-guix.json",
                "plan-nix.json",
                "manifest.json",
                "SHA256SUMS",
                "install-guix.stderr.log",
                "install-nix.stderr.log",
            }
            self.assertTrue(expected.issubset({path.name for path in output.iterdir()}))

            sums = {}
            for line in (output / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
                digest, name = line.split("  ", 1)
                sums[name] = digest
            for name, digest in sums.items():
                actual = hashlib.sha256((output / name).read_bytes()).hexdigest()
                self.assertEqual(actual, digest, name)

    def test_output_refuses_special_locations(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "wsm_hardware_check.py"),
                "--out",
                "/dev/wsm-check",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("output must not be under /dev", result.stderr)


class ReleaseBundleTests(unittest.TestCase):
    def test_bundle_is_deterministic_for_the_same_commit(self) -> None:
        from scripts.build_release_bundle import build, load_release

        release = load_release()
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first" / f"wsm-desktop-{release['version']}-source.tar.gz"
            second = Path(directory) / "second" / f"wsm-desktop-{release['version']}-source.tar.gz"
            build(release["version"], first)
            build(release["version"], second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

            with gzip_open(first) as stream:
                with tarfile.open(fileobj=stream, mode="r:") as archive:
                    names = set(archive.getnames())
            self.assertIn(f"wsm-desktop-{release['version']}/RELEASE-INFO.json", names)
            self.assertIn(f"wsm-desktop-{release['version']}/scripts/wsm_hardware_check.py", names)


def gzip_open(path: Path):  # pragma: no cover - tiny helper for readable test
    import gzip

    return gzip.open(path, "rb")


if __name__ == "__main__":
    unittest.main()
