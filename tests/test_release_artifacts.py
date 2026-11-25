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
                self.assertTrue(plan_entry["source_report_sha256_matches"])
                self.assertTrue(plan_entry["backend_id_matches_request"])
                self.assertTrue(plan_entry["confirmable_false"])

            for command in manifest["commands"]:
                self.assertIn("argv", command)
                self.assertNotIn("command", command)
                self.assertIsInstance(command["argv"], list)
            serialized = json.dumps(manifest)
            self.assertNotIn(str(output), serialized)
            self.assertIsInstance(
                manifest["safety"]["observed"]["run_as_root"],
                bool,
            )

            expected = {
                "report.json",
                "plan-guix.json",
                "plan-nix.json",
                "manifest.json",
                "SHA256SUMS",
                "install-guix.stdout.log",
                "install-guix.stderr.log",
                "install-nix.stdout.log",
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

    def test_output_refuses_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            target.mkdir()
            link = Path(directory) / "link"
            link.symlink_to(target, target_is_directory=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "wsm_hardware_check.py"),
                    "--out",
                    str(link),
                    "--report",
                    str(FIXTURE),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not a symlink", result.stderr)
            self.assertEqual(list(target.iterdir()), [])

    def test_report_must_be_a_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "wsm_hardware_check.py"),
                    "--out",
                    str(Path(directory) / "check"),
                    "--report",
                    "/dev/zero",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("report must be a regular file", result.stderr)

    def test_blocked_report_is_safely_blocked(self) -> None:
        blocked = ROOT / "tests" / "fixtures" / "hardware" / "unknown-incomplete.json"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "check"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "wsm_hardware_check.py"),
                    "--out",
                    str(output),
                    "--report",
                    str(blocked),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["overall"], "preflight-blocked")
            for backend in ("guix", "nix"):
                self.assertEqual(manifest["plans"][backend]["status"], "safely-blocked")
                self.assertFalse((output / f"plan-{backend}.json").exists())


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
