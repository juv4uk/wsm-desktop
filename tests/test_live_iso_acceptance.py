# SPDX-License-Identifier: LicenseRef-Volnist
"""Acceptance plumbing for the live image: marker in the profile, both firmwares.

The acceptance for the first bootable image is a serial marker seen in QEMU in
BIOS *and* UEFI mode. These tests check the parts that do not need QEMU: that
the profile really prints the marker, and that the harness refuses an
incomplete UEFI invocation instead of silently booting BIOS.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import qemu_boot_smoke  # noqa: E402
from qemu_boot_smoke import (  # noqa: E402
    build_qemu_command,
    copy_ovmf_vars_template,
)

MARKER = "WSM_LIVE_READY"


class LiveProfileMarkerTests(unittest.TestCase):
    def test_profile_prints_the_acceptance_marker(self) -> None:
        text = (ROOT / "systems" / "live.scm").read_text(encoding="utf-8")
        self.assertIn(MARKER, text)
        self.assertIn("/dev/console", text)

    def test_marker_service_is_registered_in_services(self) -> None:
        text = (ROOT / "systems" / "live.scm").read_text(encoding="utf-8")
        self.assertIn("wsm-live-ready-marker", text)
        self.assertIn("(operating-system-services base-os)", text)

    def test_marker_write_cannot_break_boot(self) -> None:
        """A missing console must mean 'no marker', not 'system does not boot'."""
        text = (ROOT / "systems" / "live.scm").read_text(encoding="utf-8")
        self.assertIn("(catch #t", text)

    def test_serial_console_is_on_the_kernel_command_line(self) -> None:
        text = (ROOT / "systems" / "live.scm").read_text(encoding="utf-8")
        self.assertIn("console=ttyS0", text)


class FirmwareSelectionTests(unittest.TestCase):
    def command(self, **kwargs):
        return build_qemu_command("qemu-system-x86_64", Path("/tmp/x.iso"), Path("/tmp/x.qcow2"), 1024, 1, **kwargs)

    def test_bios_is_the_default_and_has_no_pflash(self) -> None:
        command = self.command()
        self.assertFalse(any("pflash" in part for part in command))

    def test_uefi_adds_read_only_code_and_writable_vars(self) -> None:
        command = self.command(
            firmware="uefi",
            ovmf_code=Path("/tmp/OVMF_CODE.fd"),
            ovmf_vars=Path("/tmp/OVMF_VARS.fd"),
        )
        joined = " ".join(command)
        self.assertIn("readonly=on", joined)
        self.assertIn("OVMF_CODE.fd", joined)
        self.assertIn("OVMF_VARS.fd", joined)

    def test_uefi_without_vars_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.command(firmware="uefi", ovmf_code=Path("/tmp/OVMF_CODE.fd"))


class HarnessCliTests(unittest.TestCase):
    def run_harness(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "qemu_boot_smoke.py"), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_uefi_without_both_ovmf_files_is_refused_with_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            iso = root / "live.iso"
            code = root / "OVMF_CODE.fd"
            iso.write_bytes(b"not really an iso, but not empty")
            code.write_bytes(b"code image")
            result = self.run_harness(
                "--iso", str(iso), "--firmware", "uefi",
                "--ovmf-code", str(code), "--dry-run",
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--ovmf-vars", result.stderr)

    def test_vars_template_is_copied_without_modifying_the_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "OVMF_VARS.fd"
            destination = root / "private" / "OVMF_VARS.fd"
            template.write_bytes(b"separate vars template bytes")
            destination.parent.mkdir()
            copied = copy_ovmf_vars_template(template, destination)
            self.assertEqual(copied, destination)
            self.assertEqual(copied.read_bytes(), b"separate vars template bytes")
            self.assertEqual(template.read_bytes(), b"separate vars template bytes")

    def test_empty_vars_template_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "OVMF_VARS.fd"
            destination = root / "private" / "OVMF_VARS.fd"
            template.write_bytes(b"")
            destination.parent.mkdir()
            with self.assertRaises(ValueError):
                copy_ovmf_vars_template(template, destination)

    def test_actual_cli_copy_reads_vars_template_not_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            iso = root / "live.iso"
            code = root / "OVMF_CODE.fd"
            vars_template = root / "OVMF_VARS.fd"
            iso.write_bytes(b"non-empty test ISO")
            code.write_bytes(b"READ ONLY FIRMWARE CODE")
            vars_template.write_bytes(b"UEFI VARIABLE STORE TEMPLATE")
            copied = {}
            original_copyfile = qemu_boot_smoke.shutil.copyfile

            def capture_copy(source, destination):
                result = original_copyfile(source, destination)
                copied["source"] = Path(source).read_bytes()
                copied["destination"] = Path(destination).read_bytes()
                return result

            output = io.StringIO()
            with mock.patch.object(
                qemu_boot_smoke.shutil, "copyfile", side_effect=capture_copy
            ):
                with contextlib.redirect_stdout(output):
                    status = qemu_boot_smoke.main([
                        "--iso", str(iso), "--firmware", "uefi",
                        "--ovmf-code", str(code), "--ovmf-vars", str(vars_template),
                        "--dry-run",
                    ])

            self.assertEqual(status, 0)
            self.assertEqual(copied["source"], vars_template.read_bytes())
            self.assertEqual(copied["destination"], vars_template.read_bytes())
            self.assertNotEqual(copied["destination"], code.read_bytes())
            payload = json.loads(output.getvalue())
            command = " ".join(payload["qemu_command"])
            self.assertIn("unit=0,readonly=on", command)
            self.assertIn("unit=1", command)
            self.assertFalse(payload["host_efi_variables_modified"])
            self.assertTrue(payload["guest_uefi_vars_writable"])
            self.assertEqual(payload["guest_uefi_vars_source"], "private-copy-of-vars-template")
            self.assertEqual(code.read_bytes(), b"READ ONLY FIRMWARE CODE")
            self.assertEqual(vars_template.read_bytes(), b"UEFI VARIABLE STORE TEMPLATE")

    def test_uefi_cli_uses_code_and_private_copy_of_distinct_vars_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            iso = root / "live.iso"
            code = root / "OVMF_CODE.fd"
            vars_template = root / "OVMF_VARS.fd"
            iso.write_bytes(b"not really an iso, but not empty")
            code.write_bytes(b"code bytes are not vars")
            vars_template.write_bytes(b"vars bytes are distinct from code")
            result = self.run_harness(
                "--iso", str(iso), "--firmware", "uefi",
                "--ovmf-code", str(code), "--ovmf-vars", str(vars_template),
                "--dry-run",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        command = payload["qemu_command"]
        drives = [command[index + 1] for index, value in enumerate(command[:-1]) if value == "-drive"]
        self.assertEqual(len(drives), 2)
        self.assertIn(f"file={code}", drives[0])
        self.assertIn("unit=0", drives[0])
        self.assertIn("readonly=on", drives[0])
        self.assertIn("OVMF_VARS.fd", drives[1])
        self.assertIn("unit=1", drives[1])
        self.assertNotIn(f"file={vars_template}", drives[1])
        self.assertNotIn("readonly=on", drives[1])
        self.assertFalse(payload["host_efi_variables_modified"])
        self.assertTrue(payload["guest_uefi_vars_writable"])
        self.assertEqual(payload["guest_uefi_vars_source"], "private-copy-of-vars-template")

    def test_uefi_rejects_using_the_same_file_for_code_and_vars(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            iso = root / "live.iso"
            code_and_vars = root / "OVMF.fd"
            iso.write_bytes(b"not really an iso, but not empty")
            code_and_vars.write_bytes(b"one file cannot be both firmware code and vars")
            result = self.run_harness(
                "--iso", str(iso), "--firmware", "uefi",
                "--ovmf-code", str(code_and_vars), "--ovmf-vars", str(code_and_vars),
                "--dry-run",
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be separate files", result.stderr)

    def test_dry_run_reports_bios_without_guest_nvram(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".iso") as iso:
            iso.write(b"not really an iso, but not empty")
            iso.flush()
            result = self.run_harness("--iso", iso.name, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["firmware"], "bios")
        self.assertFalse(payload["host_efi_variables_modified"])
        self.assertFalse(payload["guest_uefi_vars_writable"])

    def test_acceptance_document_uses_builder_output_path_and_make_target(self) -> None:
        builder = (ROOT / "scripts" / "build_iso.sh").read_text(encoding="utf-8")
        docs = (ROOT / "docs" / "DESKTOP-PROFILE.md").read_text(encoding="utf-8")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn('ISO_OUTPUT="$OUTPUT_DIR/wsm-desktop-live.iso"', builder)
        self.assertIn("--iso build/wsm-desktop-live.iso", docs)
        self.assertNotIn("--iso build/wsm-desktop.iso", docs)
        phony = next(line for line in makefile.splitlines() if line.startswith(".PHONY"))
        self.assertIn("check-live-acceptance", phony)
        self.assertIn("image-live", phony)
        self.assertIn("image-live:", makefile)
        self.assertIn("./scripts/build_iso.sh", makefile)
        self.assertIn("make image-live", docs)



class BuildIsoArtifactTests(unittest.TestCase):
    def _fake_guix_environment(
        self, root: Path, resolved_commit: str, image_kind: str
    ) -> tuple[dict[str, str], Path]:
        fake_bin = root / "bin"
        output = root / "output"
        fake_bin.mkdir()
        output.mkdir()
        fake_guix = fake_bin / "guix"
        fake_guix.write_text(
            """#!/bin/sh
set -eu
case "$*" in
  *"-- --version"*)
    printf '%s\n' 'GNU Guix 1.6.0'
    exit 0
    ;;
  *"-- describe -f channels"*)
    printf '(list (channel (name guix) (commit "%s")))\n' "$WSM_TEST_CHANNEL_COMMIT"
    exit 0
    ;;
  *"-- system image"*)
    root_path=""
    for argument in "$@"; do
      case "$argument" in
        --root=*) root_path=$(printf '%s\n' "$argument" | sed 's/^--root=//') ;;
      esac
    done
    test -n "$root_path"
    store_path="\${root_path}.store-object"
    python3 - "$store_path" "$WSM_TEST_ISO_KIND" <<'PY'
import sys
from pathlib import Path

destination = Path(sys.argv[1])
if sys.argv[2] == "valid":
    image = bytearray(17 * 2048)
    offset = 16 * 2048
    image[offset:offset + 7] = bytes((1,)) + b"CD001" + bytes((1,))
    destination.write_bytes(image)
else:
    destination.write_bytes(b"not an ISO9660 image")
PY
    ln -s "$store_path" "$root_path"
    exit 0
    ;;
esac
printf 'unexpected fake guix arguments: %s\n' "$*" >&2
exit 97
""",
            encoding="utf-8",
        )
        fake_guix.chmod(0o755)
        environment = dict(os.environ)
        environment["PATH"] = str(fake_bin) + os.pathsep + environment.get("PATH", "")
        environment["WSM_ISO_DIR"] = str(output)
        environment["WSM_TEST_CHANNEL_COMMIT"] = resolved_commit
        environment["WSM_TEST_ISO_KIND"] = image_kind
        return environment, output

    def _locked_channel_commit(self) -> str:
        lock_text = (ROOT / "channels.lock.scm").read_text(encoding="utf-8")
        matches = re.findall(r'\(commit\s+"([0-9a-f]{40})"\)', lock_text)
        self.assertEqual(len(matches), 1)
        return matches[0]

    def _run_builder(self, environment: dict[str, str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["sh", str(ROOT / "scripts" / "build_iso.sh")],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_builder_materializes_regular_iso_and_manifest_hashes_final_file(self) -> None:
        locked_commit = self._locked_channel_commit()
        with tempfile.TemporaryDirectory() as temporary:
            environment, output = self._fake_guix_environment(
                Path(temporary), locked_commit, "valid"
            )
            result = self._run_builder(environment)
            self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)

            iso = output / "wsm-desktop-live.iso"
            gc_root = output / ".wsm-desktop-live.iso-root"
            self.assertTrue(iso.is_file())
            self.assertFalse(iso.is_symlink())
            self.assertTrue(gc_root.is_symlink())

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            artifact = manifest["artifact"]
            digest = hashlib.sha256(iso.read_bytes()).hexdigest()
            self.assertTrue(artifact["regular_file"])
            self.assertEqual(artifact["gc_root"], gc_root.name)
            self.assertEqual(artifact["size_bytes"], iso.stat().st_size)
            self.assertEqual(artifact["sha256"], digest)
            self.assertEqual(artifact["store_object_sha256"], digest)
            self.assertEqual(
                manifest["guix"]["resolved_guix_channel_commit"], locked_commit
            )

            command = manifest["build"]["command"]
            self.assertIn("-L", command)
            self.assertIn(str(ROOT), command)
            self.assertIn("--save-provenance", command)
            self.assertIn(f"--root={gc_root}", command)
            checksums = (output / "SHA256SUMS").read_text(encoding="utf-8")
            self.assertIn(f"{digest}  {iso.name}", checksums)

    def test_builder_rejects_non_iso_store_image_before_publish(self) -> None:
        locked_commit = self._locked_channel_commit()
        with tempfile.TemporaryDirectory() as temporary:
            environment, output = self._fake_guix_environment(
                Path(temporary), locked_commit, "invalid"
            )
            result = self._run_builder(environment)
            self.assertEqual(result.returncode, 4, result.stdout + "\n" + result.stderr)
            self.assertIn("ISO9660 Primary Volume Descriptor", result.stderr)
            self.assertFalse((output / "wsm-desktop-live.iso").exists())
            self.assertFalse((output / "wsm-desktop-live.iso").is_symlink())

    def test_builder_rejects_channel_resolution_that_disagrees_with_lock(self) -> None:
        locked_commit = self._locked_channel_commit()
        wrong_commit = "0" * 40 if locked_commit != "0" * 40 else "1" * 40
        with tempfile.TemporaryDirectory() as temporary:
            environment, output = self._fake_guix_environment(
                Path(temporary), wrong_commit, "valid"
            )
            result = self._run_builder(environment)
            self.assertEqual(result.returncode, 8, result.stdout + "\n" + result.stderr)
            self.assertIn("does not match channels.lock.scm", result.stderr)
            self.assertFalse((output / "wsm-desktop-live.iso").exists())


if __name__ == "__main__":
    unittest.main()
