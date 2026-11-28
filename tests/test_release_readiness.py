# SPDX-License-Identifier: LicenseRef-Volnist
"""The final release bundle is ready only when all shipped evidence agrees."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from capture_channel_resolution import capture, evidence_document  # noqa: E402


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_release_readiness", ROOT / "scripts" / "check_release_readiness.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = load_checker()


def write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def build(directory: Path, installer_executed: bool = True) -> None:
    image_path = directory / "image.iso"
    image_path.write_bytes(b"iso-image-bytes")
    iso_sha256 = checker.sha256_of(image_path)
    boot = {
        "boot_confirmed": True,
        "guest_installer_execution": installer_executed,
        "serial_clean": True,
        "serial_failure_markers": [],
        "iso_sha256": iso_sha256,
        "serial_output_tail": "...WSM_LIVE_READY...WSM_INSTALLER_OK...",
    }
    bios_path = directory / "boot-bios.json"
    uefi_path = directory / "boot-uefi.json"
    write_json(bios_path, boot)
    write_json(uefi_path, boot)

    channels_path = directory / "channels.resolved.scm"
    channels_path.write_text("(list (channel (name 'guix)))\n", encoding="utf-8")
    channel_log_path = directory / "channel-resolution.log"
    channel_command = [
        "/usr/bin/guix", "time-machine", "-C", "/repo/channels.lock.scm",
        "-L", "/repo", "--", "describe", "-f", "channels",
    ]
    channel_log_path.write_text(
        json.dumps(
            evidence_document(channel_command, channels_path.read_bytes(), b"", 0),
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    build_log_path = directory / "build.log"
    build_log_path.write_text("guix system image build completed\\n", encoding="utf-8")

    build_path = directory / "build-manifest.json"
    write_json(build_path, {
        "schema": "wsm-build/1",
        "artifact": {
            "filename": image_path.name,
            "size_bytes": image_path.stat().st_size,
            "sha256": checker.sha256_of(image_path),
        },
        "source": {"commit": "test"},
        "build": {
            "log": build_log_path.name,
            "log_sha256": checker.sha256_of(build_log_path),
            "log_bytes": build_log_path.stat().st_size,
        },
        "guix": {
            "resolved_channels_file": channels_path.name,
            "resolved_channels_sha256": checker.sha256_of(channels_path),
            "resolved_channels_bytes": channels_path.stat().st_size,
            "channel_resolution_log": channel_log_path.name,
            "channel_resolution_log_sha256": checker.sha256_of(channel_log_path),
            "channel_resolution_log_bytes": channel_log_path.stat().st_size,
            "channel_resolution_exit_status": 0,
        },
    })

    manifest = {
        "release": {"source_commit": "test"},
        "acceptance": {
            "bios": "pass",
            "uefi": "pass",
            "installer": "pass",
            "marker": "WSM_LIVE_READY",
            "installer_marker": "WSM_INSTALLER_OK",
        },
        "artifact": {
            "filename": "image.iso",
            "bytes": image_path.stat().st_size,
            "sha256": checker.sha256_of(image_path),
            "published_as": "whole",
        },
        "boot_evidence": {
            "bios_sha256": checker.sha256_of(bios_path),
            "uefi_sha256": checker.sha256_of(uefi_path),
        },
        "build_manifest_sha256": checker.sha256_of(build_path),
    }
    write_json(directory / "release-manifest.json", manifest)
    write_sums(directory)


def write_sums(
    directory: Path,
    image_assets: tuple[str, ...] = ("image.iso",),
    extra: tuple[str, ...] = (),
) -> None:
    names = (
        *image_assets,
        "build-manifest.json",
        "build.log",
        "release-manifest.json",
        "boot-bios.json",
        "boot-uefi.json",
        "channels.resolved.scm",
        "channel-resolution.log",
        *extra,
    )
    lines = []
    for name in names:
        path = directory / name
        digest = checker.sha256_of(path) if path.is_file() else "0" * 64
        lines.append(f"{digest}  {name}")
    (directory / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def rewrite_checksum(directory: Path, name: str) -> None:
    path = directory / name
    digest = checker.sha256_of(path)
    sums = directory / "SHA256SUMS"
    lines = sums.read_text(encoding="utf-8").splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.endswith(f"  {name}"):
            lines[index] = f"{digest}  {name}"
            replaced = True
    if not replaced:
        raise AssertionError(f"missing checksum entry for {name}")
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")



def refresh_after_build_manifest_change(directory: Path) -> None:
    """Keep the outer manifest and checksums consistent after fixture mutation."""
    build_path = directory / "build-manifest.json"
    release_path = directory / "release-manifest.json"
    release_manifest = json.loads(release_path.read_text(encoding="utf-8"))
    release_manifest["build_manifest_sha256"] = checker.sha256_of(build_path)
    write_json(release_path, release_manifest)
    write_sums(directory)


def make_parts(directory: Path, first: bytes = b"iso-", second: bytes = b"image-bytes") -> None:
    image = directory / "image.iso"
    payload = image.read_bytes()
    manifest_path = directory / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    part_names = ("image.iso.part000", "image.iso.part001")
    (directory / part_names[0]).write_bytes(first)
    (directory / part_names[1]).write_bytes(second)
    manifest["artifact"]["published_as"] = "parts"
    manifest["artifact"]["parts"] = list(part_names)
    manifest["artifact"]["parts_count"] = len(part_names)
    # The caller may use deliberately incorrect contents to test the combined hash.
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    image.unlink()
    (directory / "ISO-CHECKSUMS.sha256").write_text(
        "".join(
            f"{checker.sha256_of(directory / name)}  {name}\n"
            for name in part_names
        ),
        encoding="utf-8",
    )
    write_sums(directory, image_assets=part_names, extra=("ISO-CHECKSUMS.sha256",))


class ChannelResolutionCaptureTests(unittest.TestCase):
    def test_successful_resolution_with_empty_stderr_is_explicit_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_guix = root / "guix"
            fake_guix.write_text(
                "#!/bin/sh\necho \"(list (channel (name 'guix)))\"\n",
                encoding="utf-8",
            )
            fake_guix.chmod(0o755)
            stdout, stderr, status, launch_error = capture([
                str(fake_guix), "time-machine", "-C", "/repo/channels.lock.scm",
                "-L", "/repo", "--", "describe", "-f", "channels",
            ])
            document = evidence_document(
                [str(fake_guix), "time-machine", "-C", "/repo/channels.lock.scm",
                 "-L", "/repo", "--", "describe", "-f", "channels"],
                stdout, stderr, status, launch_error,
            )
            self.assertEqual(status, 0)
            self.assertIsNone(launch_error)
            self.assertTrue(stdout)
            self.assertEqual(document["stderr"]["bytes"], 0)
            self.assertEqual(document["stderr"]["text"], "")
            self.assertEqual(document["stderr"]["base64"], "")

    def test_failed_resolution_keeps_its_exit_status_and_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fake_guix = Path(temporary) / "guix"
            fake_guix.write_text(
                "#!/bin/sh\necho \"channel trust failure\" >&2\nexit 17\n",
                encoding="utf-8",
            )
            fake_guix.chmod(0o755)
            stdout, stderr, status, launch_error = capture([
                str(fake_guix), "time-machine", "-C", "/repo/channels.lock.scm",
                "-L", "/repo", "--", "describe", "-f", "channels",
            ])
            self.assertEqual(status, 17)
            self.assertIsNone(launch_error)
            self.assertIn(b"channel trust failure", stderr)

    def test_release_checker_rejects_an_empty_resolution_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            build(directory)
            log = directory / "channel-resolution.log"
            log.write_bytes(b"")
            manifest_path = directory / "build-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["guix"]["channel_resolution_log_sha256"] = checker.sha256_of(log)
            manifest["guix"]["channel_resolution_log_bytes"] = 0
            write_json(manifest_path, manifest)
            refresh_after_build_manifest_change(directory)
            found = checker.problems(directory)
            self.assertTrue(
                any("channel-resolution.log" in problem for problem in found), found
            )

    def test_release_checker_rejects_a_transcript_for_another_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            build(directory)
            log_path = directory / "channel-resolution.log"
            transcript = json.loads(log_path.read_text(encoding="utf-8"))
            transcript["command"][1] = "describe"
            write_json(log_path, transcript)
            build_manifest_path = directory / "build-manifest.json"
            build_manifest = json.loads(build_manifest_path.read_text(encoding="utf-8"))
            build_manifest["guix"]["channel_resolution_log_sha256"] = checker.sha256_of(log_path)
            build_manifest["guix"]["channel_resolution_log_bytes"] = log_path.stat().st_size
            write_json(build_manifest_path, build_manifest)
            refresh_after_build_manifest_change(directory)
            found = checker.problems(directory)
            self.assertTrue(
                any("expected locked Guix describe command" in problem for problem in found),
                found,
            )


class ReleaseReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        build(self.directory)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_a_consistent_whole_iso_bundle_is_ready(self) -> None:
        self.assertEqual(checker.problems(self.directory), [])

    def test_build_log_is_a_required_published_asset(self) -> None:
        (self.directory / "build.log").unlink()
        found = checker.problems(self.directory)
        self.assertTrue(any("missing build.log" in item for item in found), found)

    def test_build_log_symlink_is_refused(self) -> None:
        path = self.directory / "build.log"
        external = self.directory.parent / "external-build.log"
        external.write_text("external transcript\\n", encoding="utf-8")
        path.unlink()
        path.symlink_to(external)
        found = checker.problems(self.directory)
        self.assertTrue(any("build.log must not be a symlink" in item for item in found), found)

    def test_truncated_build_log_is_caught_by_recorded_byte_count(self) -> None:
        path = self.directory / "build.log"
        path.write_text("short\\n", encoding="utf-8")
        build_path = self.directory / "build-manifest.json"
        build_manifest = json.loads(build_path.read_text(encoding="utf-8"))
        build_manifest["build"]["log_sha256"] = checker.sha256_of(path)
        write_json(build_path, build_manifest)
        refresh_after_build_manifest_change(self.directory)
        rewrite_checksum(self.directory, "build.log")
        found = checker.problems(self.directory)
        self.assertTrue(any("build.log does not match build-manifest build.log_bytes" in item for item in found), found)

    def test_build_log_hash_must_match_builder_manifest(self) -> None:
        (self.directory / "build.log").write_text("changed transcript\\n", encoding="utf-8")
        rewrite_checksum(self.directory, "build.log")
        found = checker.problems(self.directory)
        self.assertTrue(
            any("build.log does not match build-manifest build.log_sha256" in item for item in found),
            found,
        )

    def test_bios_boot_evidence_without_iso_hash_is_refused(self) -> None:
        path = self.directory / "boot-bios.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record.pop("iso_sha256")
        write_json(path, record)
        rewrite_checksum(self.directory, "boot-bios.json")
        manifest_path = self.directory / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["boot_evidence"]["bios_sha256"] = checker.sha256_of(path)
        write_json(manifest_path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("boot-bios.json iso_sha256 is missing or malformed" in item for item in found), found)

    def test_uefi_boot_evidence_without_iso_hash_is_refused(self) -> None:
        path = self.directory / "boot-uefi.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record.pop("iso_sha256")
        write_json(path, record)
        rewrite_checksum(self.directory, "boot-uefi.json")
        manifest_path = self.directory / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["boot_evidence"]["uefi_sha256"] = checker.sha256_of(path)
        write_json(manifest_path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("boot-uefi.json iso_sha256 is missing or malformed" in item for item in found), found)

    def test_boot_evidence_must_be_bound_to_the_published_iso(self) -> None:
        path = self.directory / "boot-bios.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["iso_sha256"] = "0" * 64
        write_json(path, record)
        rewrite_checksum(self.directory, "boot-bios.json")
        manifest_path = self.directory / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["boot_evidence"]["bios_sha256"] = checker.sha256_of(path)
        write_json(manifest_path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(
            any("boot evidence iso_sha256 != release-manifest artifact sha256" in item for item in found),
            found,
        )

    def test_uefi_boot_evidence_must_be_bound_to_the_published_iso(self) -> None:
        path = self.directory / "boot-uefi.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["iso_sha256"] = "0" * 64
        write_json(path, record)
        rewrite_checksum(self.directory, "boot-uefi.json")
        manifest_path = self.directory / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["boot_evidence"]["uefi_sha256"] = checker.sha256_of(path)
        write_json(manifest_path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(
            any("boot-uefi.json boot evidence iso_sha256 != release-manifest artifact sha256" in item
                for item in found),
            found,
        )

    def test_boot_evidence_without_serial_clean_is_refused(self) -> None:
        path = self.directory / "boot-bios.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record.pop("serial_clean")
        write_json(path, record)
        rewrite_checksum(self.directory, "boot-bios.json")
        manifest_path = self.directory / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["boot_evidence"]["bios_sha256"] = checker.sha256_of(path)
        write_json(manifest_path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(
            any("boot-bios.json has serial_clean false or missing" in item for item in found),
            found,
        )

    def test_boot_evidence_with_serial_segfault_is_refused_even_with_markers(self) -> None:
        path = self.directory / "boot-uefi.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["serial_failure_markers"] = ["segfault"]
        record["serial_clean"] = False
        write_json(path, record)
        rewrite_checksum(self.directory, "boot-uefi.json")
        manifest_path = self.directory / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["boot_evidence"]["uefi_sha256"] = checker.sha256_of(path)
        write_json(manifest_path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(
            any("boot-uefi.json contains serial failure markers: segfault" in item for item in found),
            found,
        )

    def test_build_manifest_artifact_filename_must_match_release_manifest(self) -> None:
        build_path = self.directory / "build-manifest.json"
        build_manifest = json.loads(build_path.read_text(encoding="utf-8"))
        build_manifest["artifact"]["filename"] = "other.iso"
        write_json(build_path, build_manifest)
        refresh_after_build_manifest_change(self.directory)
        found = checker.problems(self.directory)
        self.assertTrue(any("artifact filename" in item for item in found), found)

    def test_build_manifest_artifact_sha256_must_match_release_manifest(self) -> None:
        build_path = self.directory / "build-manifest.json"
        build_manifest = json.loads(build_path.read_text(encoding="utf-8"))
        build_manifest["artifact"]["sha256"] = "0" * 64
        write_json(build_path, build_manifest)
        refresh_after_build_manifest_change(self.directory)
        found = checker.problems(self.directory)
        self.assertTrue(any("build-manifest artifact sha256" in item for item in found), found)

    def test_build_manifest_artifact_size_must_match_release_manifest(self) -> None:
        build_path = self.directory / "build-manifest.json"
        build_manifest = json.loads(build_path.read_text(encoding="utf-8"))
        build_manifest["artifact"]["size_bytes"] += 1
        write_json(build_path, build_manifest)
        refresh_after_build_manifest_change(self.directory)
        found = checker.problems(self.directory)
        self.assertTrue(any("artifact size_bytes" in item for item in found), found)

    def test_release_workflow_binds_build_source_to_github_sha(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release-minimal-live.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('"$DIST/build-manifest.json" "$GITHUB_SHA"', workflow)
        self.assertIn('commit != sys.argv[2]', workflow)

    def test_build_and_release_source_commits_must_match(self) -> None:
        build_path = self.directory / "build-manifest.json"
        build_manifest = json.loads(build_path.read_text(encoding="utf-8"))
        build_manifest["source"]["commit"] = "different-source-commit"
        write_json(build_path, build_manifest)
        refresh_after_build_manifest_change(self.directory)
        found = checker.problems(self.directory)
        self.assertTrue(any("source.commit !=" in item for item in found), found)

    def test_symlinked_bundle_root_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            link = Path(temporary) / "bundle-link"
            link.symlink_to(self.directory, target_is_directory=True)
            self.assertEqual(
                checker.problems(link),
                ["release bundle directory must not be a symlink"],
            )

    def test_channel_resolution_log_and_source_are_required_release_assets(self) -> None:
        (self.directory / "channel-resolution.log").unlink()
        found = checker.problems(self.directory)
        self.assertTrue(any("missing channel-resolution.log" in item for item in found), found)

    def test_channel_resolution_log_hash_must_match_build_manifest(self) -> None:
        build_path = self.directory / "build-manifest.json"
        build_manifest = json.loads(build_path.read_text(encoding="utf-8"))
        build_manifest["guix"]["channel_resolution_log_sha256"] = "0" * 64
        write_json(build_path, build_manifest)
        refresh_after_build_manifest_change(self.directory)
        found = checker.problems(self.directory)
        self.assertTrue(
            any("guix.channel_resolution_log_sha256" in item for item in found), found
        )

    def test_resolved_channels_hash_must_match_build_manifest(self) -> None:
        build_path = self.directory / "build-manifest.json"
        build_manifest = json.loads(build_path.read_text(encoding="utf-8"))
        build_manifest["guix"]["resolved_channels_sha256"] = "0" * 64
        write_json(build_path, build_manifest)
        refresh_after_build_manifest_change(self.directory)
        found = checker.problems(self.directory)
        self.assertTrue(
            any("guix.resolved_channels_sha256" in item for item in found), found
        )

    def test_channel_resolution_log_byte_count_must_match(self) -> None:
        build_path = self.directory / "build-manifest.json"
        build_manifest = json.loads(build_path.read_text(encoding="utf-8"))
        build_manifest["guix"]["channel_resolution_log_bytes"] = 1
        write_json(build_path, build_manifest)
        refresh_after_build_manifest_change(self.directory)
        found = checker.problems(self.directory)
        self.assertTrue(any("channel_resolution_log_bytes" in item for item in found), found)

    def test_channel_resolution_exit_status_must_be_zero(self) -> None:
        build_path = self.directory / "build-manifest.json"
        build_manifest = json.loads(build_path.read_text(encoding="utf-8"))
        build_manifest["guix"]["channel_resolution_exit_status"] = 1
        write_json(build_path, build_manifest)
        refresh_after_build_manifest_change(self.directory)
        found = checker.problems(self.directory)
        self.assertTrue(any("channel resolution did not exit successfully" in item for item in found), found)

    def test_installer_acceptance_without_execution_is_refused(self) -> None:
        build(self.directory, installer_executed=False)
        found = checker.problems(self.directory)
        self.assertTrue(any("guest_installer_execution false" in item for item in found), found)

    def test_installer_claim_without_serial_marker_is_refused(self) -> None:
        record_path = self.directory / "boot-bios.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["serial_output_tail"] = "WSM_LIVE_READY only"
        write_json(record_path, record)
        rewrite_checksum(self.directory, "boot-bios.json")
        manifest_path = self.directory / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["boot_evidence"]["bios_sha256"] = checker.sha256_of(record_path)
        write_json(manifest_path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("never showed WSM_INSTALLER_OK" in item for item in found), found)

    def test_missing_manifest_marker_is_refused(self) -> None:
        path = self.directory / "release-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["acceptance"]["marker"] = ""
        write_json(path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("acceptance.marker is missing" in item for item in found), found)

    def test_missing_installer_marker_is_refused(self) -> None:
        path = self.directory / "release-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["acceptance"]["installer_marker"] = None
        write_json(path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("acceptance.installer_marker is missing" in item for item in found), found)

    def test_missing_acceptance_pass_is_refused(self) -> None:
        path = self.directory / "release-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["acceptance"]["uefi"] = "unknown"
        write_json(path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("acceptance.uefi is not pass" in item for item in found), found)

    def test_a_missing_required_evidence_asset_is_refused(self) -> None:
        (self.directory / "boot-uefi.json").unlink()
        found = checker.problems(self.directory)
        self.assertTrue(any("missing boot-uefi.json" in item for item in found), found)

    def test_a_missing_sha256sums_listed_asset_is_refused(self) -> None:
        write_sums(self.directory, extra=("build-metadata.json",))
        found = checker.problems(self.directory)
        self.assertTrue(
            any("build-metadata.json is listed in SHA256SUMS but is absent" in item for item in found),
            found,
        )

    def test_a_corrupted_image_is_refused(self) -> None:
        (self.directory / "image.iso").write_bytes(b"tampered")
        found = checker.problems(self.directory)
        self.assertTrue(any("image.iso does not match its recorded hash" in item for item in found), found)

    def test_an_absent_image_is_not_ready_by_default(self) -> None:
        (self.directory / "image.iso").unlink()
        found = checker.problems(self.directory)
        self.assertTrue(any("image.iso is listed in SHA256SUMS but is absent" in item for item in found), found)

    def test_metadata_only_is_explicitly_not_ready(self) -> None:
        (self.directory / "image.iso").unlink()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = checker.main([str(self.directory), "--metadata-only"])
        self.assertEqual(result, 2)
        self.assertIn("NOT_READY", output.getvalue())

    def test_a_consistent_multipart_bundle_is_ready(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], payload[4:])
        self.assertEqual(checker.problems(self.directory), [])

    def test_a_missing_multipart_part_is_refused(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], payload[4:])
        (self.directory / "image.iso.part001").unlink()
        found = checker.problems(self.directory)
        self.assertTrue(
            any("image.iso.part001 is listed in SHA256SUMS but is absent" in item for item in found),
            found,
        )

    def test_missing_multipart_sidecar_is_refused(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], payload[4:])
        (self.directory / "ISO-CHECKSUMS.sha256").unlink()
        found = checker.problems(self.directory)
        self.assertTrue(
            any("ISO-CHECKSUMS.sha256 is listed in SHA256SUMS but is absent" in item for item in found),
            found,
        )

    def test_multipart_sidecar_contents_are_verified(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], payload[4:])
        sidecar = self.directory / "ISO-CHECKSUMS.sha256"
        sidecar.write_text("0" * 64 + "  image.iso.part000\n", encoding="utf-8")
        rewrite_checksum(self.directory, "ISO-CHECKSUMS.sha256")
        found = checker.problems(self.directory)
        self.assertTrue(
            any("ISO-CHECKSUMS.sha256 does not match" in item for item in found),
            found,
        )

    def test_extra_multipart_piece_is_refused(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], payload[4:])
        (self.directory / "image.iso.part002").write_bytes(b"extra")
        found = checker.problems(self.directory)
        self.assertTrue(any("unexpected split parts" in item for item in found), found)

    def test_multipart_part_numbers_must_be_contiguous(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], payload[4:])
        old_part = self.directory / "image.iso.part001"
        new_part = self.directory / "image.iso.part002"
        old_part.rename(new_part)
        manifest_path = self.directory / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifact"]["parts"][1] = new_part.name
        write_json(manifest_path, manifest)
        sidecar = self.directory / "ISO-CHECKSUMS.sha256"
        sidecar.write_text(
            "".join(
                f"{checker.sha256_of(self.directory / name)}  {name}\n"
                for name in manifest["artifact"]["parts"]
            ),
            encoding="utf-8",
        )
        write_sums(
            self.directory,
            image_assets=tuple(manifest["artifact"]["parts"]),
            extra=("ISO-CHECKSUMS.sha256",),
        )
        found = checker.problems(self.directory)
        self.assertTrue(any("not contiguously numbered" in item for item in found), found)

    def test_missing_build_manifest_checksum_row_is_refused(self) -> None:
        sums = self.directory / "SHA256SUMS"
        lines = [
            line for line in sums.read_text(encoding="utf-8").splitlines()
            if not line.endswith("  build-manifest.json")
        ]
        sums.write_text("\n".join(lines) + "\n", encoding="utf-8")
        found = checker.problems(self.directory)
        self.assertTrue(any("build-manifest.json is not listed" in item for item in found), found)

    def test_missing_boot_evidence_hash_fields_are_refused(self) -> None:
        for key in ("bios_sha256", "uefi_sha256"):
            with self.subTest(key=key):
                manifest_path = self.directory / "release-manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["boot_evidence"].pop(key)
                write_json(manifest_path, manifest)
                rewrite_checksum(self.directory, "release-manifest.json")
                found = checker.problems(self.directory)
                self.assertTrue(any(f"boot_evidence.{key} is missing" in item for item in found), found)
                build(self.directory)

    def test_every_acceptance_state_is_mandatory(self) -> None:
        for key in ("bios", "uefi", "installer"):
            with self.subTest(key=key):
                manifest_path = self.directory / "release-manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["acceptance"].pop(key)
                write_json(manifest_path, manifest)
                rewrite_checksum(self.directory, "release-manifest.json")
                found = checker.problems(self.directory)
                self.assertTrue(any(f"acceptance.{key} is not pass" in item for item in found), found)
                build(self.directory)

    def test_boot_json_whitespace_change_without_checksum_update_is_refused(self) -> None:
        path = self.directory / "boot-bios.json"
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        found = checker.problems(self.directory)
        self.assertTrue(
            any("boot-bios.json does not match its recorded hash" in item for item in found),
            found,
        )

    def test_multipart_contents_must_reconstruct_the_declared_iso(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], b"wrong")
        found = checker.problems(self.directory)
        self.assertTrue(
            any("concatenated artifact parts do not match" in item for item in found),
            found,
        )

    def test_multipart_parts_must_be_in_lexical_order(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], payload[4:])
        path = self.directory / "release-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["artifact"]["parts"].reverse()
        write_json(path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("not in lexical concatenation order" in item for item in found), found)

    def test_build_manifest_digest_must_match(self) -> None:
        path = self.directory / "release-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["build_manifest_sha256"] = "0" * 64
        write_json(path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("build_manifest_sha256" in item for item in found), found)

    def test_boot_evidence_digest_must_match(self) -> None:
        path = self.directory / "release-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["boot_evidence"]["bios_sha256"] = "0" * 64
        write_json(path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("boot_evidence.bios_sha256" in item for item in found), found)

    def test_unsafe_asset_paths_are_refused(self) -> None:
        sums = self.directory / "SHA256SUMS"
        line = f"{'0' * 64}  ../outside"
        sums.write_text(sums.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
        found = checker.problems(self.directory)
        self.assertTrue(any("unsafe asset name" in item for item in found), found)

    def test_symlink_assets_are_refused(self) -> None:
        image = self.directory / "image.iso"
        image.unlink()
        image.symlink_to(self.directory / "build-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("image.iso must not be a symlink" in item for item in found), found)

    def test_malformed_sums_are_refused(self) -> None:
        (self.directory / "SHA256SUMS").write_text("not a checksum line\n", encoding="utf-8")
        found = checker.problems(self.directory)
        self.assertTrue(any("malformed SHA256SUMS line 1" in item for item in found), found)

    def test_duplicate_sums_entries_are_refused(self) -> None:
        sums = self.directory / "SHA256SUMS"
        line = next(
            line for line in sums.read_text(encoding="utf-8").splitlines()
            if line.endswith("  image.iso")
        )
        sums.write_text(sums.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
        found = checker.problems(self.directory)
        self.assertTrue(any("duplicate SHA256SUMS entry: image.iso" in item for item in found), found)


if __name__ == "__main__":
    unittest.main()
