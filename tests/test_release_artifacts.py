# SPDX-License-Identifier: LicenseRef-Volnist
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
from types import SimpleNamespace
from unittest.mock import patch
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
            self.assertEqual(set(manifest["plans"]), {"guix"})
            for backend in ("guix",):
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
                "manifest.json",
                "SHA256SUMS",
                "install-guix.stdout.log",
                "install-guix.stderr.log",
            }
            self.assertTrue(expected.issubset({path.name for path in output.iterdir()}))
            self.assertFalse((output / "plan-nix.json").exists())
            self.assertFalse((output / "install-nix.stdout.log").exists())
            self.assertFalse((output / "install-nix.stderr.log").exists())

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

    def test_output_permission_failure_fails_closed(self) -> None:
        from scripts.wsm_hardware_check import prepare_output

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "private"
            with patch(
                "scripts.wsm_hardware_check.os.chmod",
                side_effect=PermissionError("permission denied"),
            ):
                with self.assertRaisesRegex(SystemExit, "cannot enforce output directory mode 0700"):
                    prepare_output(str(output))
            self.assertTrue(output.is_dir())

    def test_output_mode_mismatch_fails_closed(self) -> None:
        from scripts.wsm_hardware_check import prepare_output

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "existing"
            output.mkdir()
            os.chmod(output, 0o755)
            with patch("scripts.wsm_hardware_check.os.chmod", return_value=None):
                with self.assertRaisesRegex(SystemExit, "output directory mode is"):
                    prepare_output(str(output))
            self.assertEqual(list(output.iterdir()), [])

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


    def test_bundle_uses_the_exact_commit_recorded_in_manifest(self) -> None:
        from scripts.build_release_bundle import build, load_release

        pinned_commit = "1" * 40
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / f"wsm-desktop-{load_release()['version']}-source.tar.gz"
            with (
                patch(
                    "scripts.build_release_bundle.git_output",
                    side_effect=[pinned_commit, ""],
                ),
                patch(
                    "scripts.build_release_bundle.subprocess.run",
                    return_value=SimpleNamespace(stdout=b"synthetic tar archive"),
                ) as archive_run,
            ):
                manifest = build(load_release()["version"], output)

            archive_argv = archive_run.call_args.args[0]
            self.assertEqual(archive_argv[-1], pinned_commit)
            self.assertEqual(manifest["source_commit"], pinned_commit)
            self.assertIn(pinned_commit, manifest["build"]["command"])

    def test_bundle_rolls_back_when_sha256s_fsync_fails(self) -> None:
        from scripts.build_release_bundle import build, load_release

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / f"wsm-desktop-{load_release()['version']}-source.tar.gz"
            with (
                patch(
                    "scripts.build_release_bundle.git_output",
                    side_effect=["2" * 40, ""],
                ),
                patch(
                    "scripts.build_release_bundle.subprocess.run",
                    return_value=SimpleNamespace(stdout=b"synthetic tar archive"),
                ),
                patch(
                    "scripts.build_release_bundle.os.fsync",
                    side_effect=[None, OSError("injected SHA256SUMS fsync failure")],
                ),
            ):
                with self.assertRaisesRegex(OSError, "SHA256SUMS fsync failure"):
                    build(load_release()["version"], output)

            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_bundle_rolls_back_when_manifest_fsync_fails(self) -> None:
        from scripts.build_release_bundle import build, load_release

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / f"wsm-desktop-{load_release()['version']}-source.tar.gz"
            with (
                patch(
                    "scripts.build_release_bundle.git_output",
                    side_effect=["3" * 40, ""],
                ),
                patch(
                    "scripts.build_release_bundle.subprocess.run",
                    return_value=SimpleNamespace(stdout=b"synthetic tar archive"),
                ),
                patch(
                    "scripts.build_release_bundle.os.fsync",
                    side_effect=[
                        None,
                        None,
                        OSError("injected manifest fsync failure"),
                    ],
                ),
            ):
                with self.assertRaisesRegex(OSError, "manifest fsync failure"):
                    build(load_release()["version"], output)

            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_bundle_refuses_special_filesystem_output_locations(self) -> None:
        from scripts.build_release_bundle import _prepare_artifact_paths, load_release

        version = load_release()["version"]
        filename = f"wsm-desktop-{version}-source.tar.gz"
        for special in (Path("/dev"), Path("/proc"), Path("/sys")):
            with self.subTest(special=str(special)):
                with self.assertRaisesRegex(SystemExit, "output directory must not be under"):
                    _prepare_artifact_paths(version, special / filename)

    def test_bundle_refuses_existing_manifest_before_creating_tarball(self) -> None:
        from scripts.build_release_bundle import build, load_release

        release = load_release()
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            output = parent / f"wsm-desktop-{release['version']}-source.tar.gz"
            manifest = parent / "release-manifest.json"
            manifest.write_text("preserve existing manifest", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "refusing to overwrite existing artifact"):
                build(release["version"], output)
            self.assertFalse(output.exists())
            self.assertEqual(
                manifest.read_text(encoding="utf-8"),
                "preserve existing manifest",
            )

    def test_bundle_refuses_existing_tarball_without_overwriting(self) -> None:
        from scripts.build_release_bundle import build, load_release

        release = load_release()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / f"wsm-desktop-{release['version']}-source.tar.gz"
            output.write_bytes(b"keep this file")
            with self.assertRaisesRegex(SystemExit, "refusing to overwrite existing artifact"):
                build(release["version"], output)
            self.assertEqual(output.read_bytes(), b"keep this file")

    def test_bundle_refuses_existing_sidecar_before_creating_tarball(self) -> None:
        from scripts.build_release_bundle import build, load_release

        release = load_release()
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            output = parent / f"wsm-desktop-{release['version']}-source.tar.gz"
            sums = parent / "SHA256SUMS"
            sums.write_text("preserve existing checksum", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "refusing to overwrite existing artifact"):
                build(release["version"], output)
            self.assertFalse(output.exists())
            self.assertEqual(sums.read_text(encoding="utf-8"), "preserve existing checksum")

    def test_bundle_refuses_symlinked_output_parent(self) -> None:
        from scripts.build_release_bundle import build, load_release

        release = load_release()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actual = root / "actual"
            actual.mkdir()
            alias = root / "alias"
            alias.symlink_to(actual, target_is_directory=True)
            output = alias / f"wsm-desktop-{release['version']}-source.tar.gz"
            with self.assertRaisesRegex(SystemExit, "symlink path components"):
                build(release["version"], output)
            self.assertEqual(list(actual.iterdir()), [])

    def test_bundle_refuses_repository_paths_outside_build(self) -> None:
        from scripts.build_release_bundle import build, load_release

        release = load_release()
        output = ROOT / f"wsm-desktop-{release['version']}-source.tar.gz"
        self.assertFalse(output.exists())
        with self.assertRaisesRegex(SystemExit, "inside the repository is allowed only under build"):
            build(release["version"], output)
        self.assertFalse(output.exists())

    def test_bundle_refuses_noncanonical_output_filename(self) -> None:
        from scripts.build_release_bundle import build, load_release

        release = load_release()
        readme = ROOT / "README.md"
        original = readme.read_bytes()
        with self.assertRaisesRegex(SystemExit, "--output filename must be exactly"):
            build(release["version"], readme)
        self.assertEqual(readme.read_bytes(), original)


    def test_output_name_must_match_the_published_asset(self) -> None:
        """A custom --output would put a name in SHA256SUMS nobody can verify."""
        from scripts.build_release_bundle import build, load_release

        release = load_release()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit) as caught:
                build(release["version"], Path(directory) / "bundle.tar.gz")
            self.assertIn("wsm-desktop-", str(caught.exception))
            self.assertIn("--output filename", str(caught.exception))

            canonical = Path(directory) / f"wsm-desktop-{release['version']}-source.tar.gz"
            build(release["version"], canonical)
            sums = (canonical.parent / "SHA256SUMS").read_text(encoding="utf-8")
            self.assertIn(f"  {canonical.name}", sums)

def gzip_open(path: Path):  # pragma: no cover - tiny helper for readable test
    import gzip

    return gzip.open(path, "rb")


if __name__ == "__main__":
    unittest.main()