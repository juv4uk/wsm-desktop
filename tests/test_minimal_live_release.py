# SPDX-License-Identifier: LicenseRef-Volnist
"""Behavioral tests for the compact live installer entrypoint and release gate."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from qemu_boot_smoke import main as qemu_main  # noqa: E402


class MinimalLiveProfileTests(unittest.TestCase):
    def test_make_target_selects_the_minimal_profile(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("image-live-minimal:", makefile)
        self.assertIn("WSM_LIVE_PROFILE=systems/live-minimal.scm", makefile)

    def test_profile_has_a_dedicated_unprivileged_console_login(self) -> None:
        profile = (ROOT / "systems" / "live-minimal.scm").read_text(encoding="utf-8")
        self.assertIn('(auto-login "wsm")', profile)
        self.assertIn('(mingetty-configuration-tty config) "tty2"', profile)
        self.assertIn("wpa-supplicant-service-type", profile)
        self.assertNotIn("plasma-desktop-service-type", profile)

    def test_guix_package_installs_python_runtime_and_wsm_commands(self) -> None:
        package = (ROOT / "wsm" / "packages" / "wsm.scm").read_text(encoding="utf-8")
        for path in ("scripts/wsm-hwcheck.sh","scripts/wsm-install.sh","scripts/wsm-install-live.sh"):
            with self.subTest(path=path):
                self.assertIn(path, package)
        self.assertIn("(propagated-inputs (list python python-jsonschema))", package)
        self.assertIn('(version "0.1.0-rc3")', package)

    def test_release_workflow_has_size_and_two_firmware_gates(self) -> None:
        workflow = (ROOT / ".github/workflows/release-minimal-live.yml").read_text(encoding="utf-8")
        for expected in ("make image-live-minimal","2147483647","--firmware bios",
                         "--firmware uefi","--boot-marker WSM_LIVE_READY",
                         "gh release create","RELEASE-REQUEST.txt"):
            with self.subTest(expected=expected):
                self.assertIn(expected, workflow)

    def test_ci_pushes_only_from_main(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("branches: [main]", workflow)

    def test_locked_guix_load_path_is_applied_at_both_cli_levels(self) -> None:
        builder = (ROOT / "scripts" / "build_iso.sh").read_text(encoding="utf-8")
        self.assertIn(
            'guix time-machine -C "$LOCK" -L "$ROOT" -- system -L "$ROOT" image',
            builder,
        )
        self.assertIn('guix time-machine -C "$LOCK" -L "$ROOT" -- describe -f channels', builder)
        self.assertNotIn('guix time-machine -C "$LOCK" -- -L "$ROOT"', builder)
        self.assertIn(
            '"guix", "time-machine", "-C", str(lock), "-L", str(repo_root), "--", '
            '"system", "-L", str(repo_root), "image"',
            builder,
        )
        self.assertIn('WSM_REPO_ROOT="$ROOT"', builder)
        self.assertIn('repo_root = Path(os.environ["WSM_REPO_ROOT"])', builder)

        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        evaluation = makefile.split("check-guix-eval:", 1)[1].split("\n\n", 1)[0]
        self.assertIn(
            "-C channels.lock.scm -L . -- system -L . build systems/live-minimal.scm --dry-run",
            evaluation,
        )
        self.assertIn(
            "-C channels.lock.scm -L . -- system -L . build systems/desktop.scm --dry-run",
            evaluation,
        )
        self.assertIn(
            "-C channels.lock.scm -L . -- home -L . build systems/home.scm --dry-run",
            evaluation,
        )
        self.assertIn(
            "-C channels/compatibility.lock.scm -L . -- system -L . build systems/live-compat.scm --dry-run",
            evaluation,
        )
        self.assertIn("(gnu system locale)", (ROOT / "systems" / "live-minimal.scm").read_text(encoding="utf-8"))

    def test_release_request_pins_one_tag_and_ignores_comments(self) -> None:
        lines = (ROOT / "RELEASE-REQUEST.txt").read_text(encoding="utf-8").splitlines()
        requested = [line.split("#", 1)[0].strip() for line in lines]
        tags = [line for line in requested if line]
        self.assertEqual(tags, ["0.1.0-rc3-minimal-live"])

    def test_release_workflow_requires_exactly_one_non_comment_tag(self) -> None:
        workflow = (ROOT / ".github/workflows/release-minimal-live.yml").read_text(encoding="utf-8")
        self.assertIn("mapfile -t REQUEST_TAGS", workflow)
        self.assertIn('${#REQUEST_TAGS[@]}', workflow)
        self.assertIn("sed -e 's/[[:space:]]*#.*$//'", workflow)


class LiveInstallerLauncherTests(unittest.TestCase):
    def test_launcher_runs_preflight_and_tui_then_cleans_private_report(self) -> None:
        launcher = ROOT / "scripts/wsm-install-live.sh"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            report_path_file = root / "report-path.txt"
            argument_file = root / "installer-args.txt"
            collector = fake_bin / "wsm-hwcheck"
            collector.write_text(
                """#!/bin/sh
set -eu
[ "$1" = "--output" ]
printf '%s\\n' "$2" > "$WSM_TEST_REPORT_PATH_FILE"
printf '{"fixture": true}\\n' > "$2"
""", encoding="utf-8")
            installer = fake_bin / "wsm-install"
            installer.write_text(
                """#!/bin/sh
set -eu
[ "$1" = "--preflight" ]
[ "$2" = "--dry-run" ]
[ "$3" = "--report" ]
report="$4"
[ -f "$report" ]
[ "$(stat -c '%a' "$(dirname "$report")")" = "700" ]
[ "$5" = "--backend" ]
[ "$6" = "guix" ]
[ "$7" = "--tui" ]
printf '%s\\n' "$@" > "$WSM_TEST_INSTALLER_ARGS_FILE"
""", encoding="utf-8")
            collector.chmod(0o755)
            installer.chmod(0o755)
            env = dict(os.environ)
            env.update({
                "PATH": str(fake_bin) + os.pathsep + env.get("PATH",""),
                "WSM_TEST_REPORT_PATH_FILE": str(report_path_file),
                "WSM_TEST_INSTALLER_ARGS_FILE": str(argument_file),
            })
            result = subprocess.run(["sh",str(launcher)],cwd=ROOT,env=env,
                                    capture_output=True,text=True,check=False)
            self.assertEqual(result.returncode,0,result.stdout+"\n"+result.stderr)
            report_path = Path(report_path_file.read_text(encoding="utf-8").strip())
            self.assertTrue(argument_file.is_file())
            self.assertEqual(Path(argument_file.read_text(encoding="utf-8").splitlines()[3]),report_path)
            self.assertFalse(report_path.exists())
            self.assertFalse(report_path.parent.exists())


class UefiEvidenceTests(unittest.TestCase):
    def test_uefi_uses_separate_code_and_private_vars_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            iso=root/"live.iso"
            code=root/"OVMF_CODE.fd"
            vars_template=root/"VARS_TEMPLATE.fd"
            iso.write_bytes(b"placeholder ISO")
            code.write_bytes(b"CODE firmware")
            vars_template.write_bytes(b"VARS template")
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                status=qemu_main(["--iso",str(iso),"--firmware","uefi",
                                  "--ovmf-code",str(code),"--ovmf-vars",str(vars_template),
                                  "--dry-run"])
            self.assertEqual(status,0)
            payload=json.loads(output.getvalue())
            joined=" ".join(payload["qemu_command"])
            self.assertIn(f"file={code}",joined)
            self.assertIn("readonly=on",joined)
            self.assertIn("OVMF_VARS.fd",joined)
            self.assertNotIn(f"file={vars_template}",joined)
            self.assertTrue(payload["guest_uefi_vars_writable"])
            self.assertFalse(payload["host_efi_variables_modified"])
            self.assertEqual(vars_template.read_bytes(),b"VARS template")
            self.assertEqual(code.read_bytes(),b"CODE firmware")

    def test_uefi_without_vars_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso=Path(temporary)/"live.iso"
            iso.write_bytes(b"placeholder")
            error=io.StringIO()
            with contextlib.redirect_stderr(error):
                status=qemu_main(["--iso",str(iso),"--firmware","uefi",
                                  "--ovmf-code",str(iso),"--dry-run"])
            self.assertEqual(status,2)
            self.assertIn("--ovmf-vars",error.getvalue())


if __name__ == "__main__":
    unittest.main()
