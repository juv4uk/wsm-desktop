# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the Hardware Preview release helpers."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE = ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json"


class HardwareCheckScriptTests(unittest.TestCase):
    def test_output_chmod_failure_is_fatal(self) -> None:
        from scripts.wsm_hardware_check import prepare_output

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "existing"
            output.mkdir(mode=0o755)
            os.chmod(output, 0o755)
            with patch(
                "scripts.wsm_hardware_check.os.chmod",
                side_effect=PermissionError("simulated permission denial"),
            ):
                with self.assertRaisesRegex(SystemExit, "cannot secure output directory"):
                    prepare_output(str(output))
            self.assertEqual(list(output.iterdir()), [])

    def test_output_mode_must_be_exactly_private(self) -> None:
        from scripts.wsm_hardware_check import prepare_output

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "existing"
            output.mkdir(mode=0o755)
            os.chmod(output, 0o755)
            with patch("scripts.wsm_hardware_check.os.chmod", return_value=None):
                with self.assertRaisesRegex(SystemExit, "permissions must be exactly 0700"):
                    prepare_output(str(output))
            self.assertEqual(list(output.iterdir()), [])

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
    def _output_path(self, directory: str | Path, version: str) -> Path:
        return Path(directory) / f"wsm-desktop-{version}-source.tar.gz"

    def test_bundle_rejects_noncanonical_output_name(self) -> None:
        from scripts.build_release_bundle import build, load_release

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SystemExit, "output filename must be"):
                build(load_release()["version"], Path(directory) / "custom-name.tar.gz")

    def test_bundle_refuses_output_inside_repository_tree(self) -> None:
        from scripts.build_release_bundle import build, load_release

        release = load_release()
        output = self._output_path(ROOT, release["version"])
        with self.assertRaisesRegex(SystemExit, "outside the repository tree"):
            build(release["version"], output)
        self.assertFalse(output.exists())

    def test_output_name_must_match_the_published_asset(self) -> None:
        """A custom --output would put a name in SHA256SUMS nobody downloads."""
        from scripts.build_release_bundle import build, load_release

        release = load_release()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit) as caught:
                build(release["version"], Path(directory) / "bundle.tar.gz")
            self.assertIn("wsm-desktop-", str(caught.exception))
            self.assertIn("sha256sum -c", str(caught.exception))

            canonical = self._output_path(directory, release["version"])
            build(release["version"], canonical)
            sums = (canonical.parent / "SHA256SUMS").read_text(encoding="utf-8")
            self.assertIn(f"  {canonical.name}", sums)

    def test_bundle_never_overwrites_existing_archive(self) -> None:
        from scripts.build_release_bundle import build, load_release

        with tempfile.TemporaryDirectory() as directory:
            release = load_release()
            output = self._output_path(directory, release["version"])
            output.write_bytes(b"keep this existing file")
            with self.assertRaisesRegex(SystemExit, "refusing to overwrite"):
                build(release["version"], output)
            self.assertEqual(output.read_bytes(), b"keep this existing file")

    def test_bundle_never_overwrites_existing_sibling_artifacts(self) -> None:
        from scripts.build_release_bundle import build, load_release

        for sibling_name in ("SHA256SUMS", "release-manifest.json"):
            with self.subTest(sibling=sibling_name), tempfile.TemporaryDirectory() as directory:
                release = load_release()
                output = self._output_path(directory, release["version"])
                sibling = Path(directory) / sibling_name
                sibling.write_bytes(b"keep sibling")
                with self.assertRaisesRegex(SystemExit, "refusing to overwrite"):
                    build(release["version"], output)
                self.assertEqual(sibling.read_bytes(), b"keep sibling")
                self.assertFalse(output.exists())

    def test_bundle_refuses_symlink_artifact_paths(self) -> None:
        from scripts.build_release_bundle import build, load_release

        with tempfile.TemporaryDirectory() as directory:
            release = load_release()
            output = self._output_path(directory, release["version"])
            target = Path(directory) / "sentinel"
            target.write_bytes(b"do not touch")
            (Path(directory) / "release-manifest.json").symlink_to(target)
            with self.assertRaisesRegex(SystemExit, "refusing to overwrite"):
                build(release["version"], output)
            self.assertEqual(target.read_bytes(), b"do not touch")
            self.assertFalse(output.exists())

    def test_bundle_refuses_symlink_parent_components(self) -> None:
        from scripts.build_release_bundle import build, load_release

        with tempfile.TemporaryDirectory() as directory:
            real = Path(directory) / "real"
            real.mkdir()
            link = Path(directory) / "linked"
            link.symlink_to(real, target_is_directory=True)
            release = load_release()
            output = self._output_path(link, release["version"])
            with self.assertRaisesRegex(SystemExit, "contains a symlink"):
                build(release["version"], output)
            self.assertEqual(list(real.iterdir()), [])

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
