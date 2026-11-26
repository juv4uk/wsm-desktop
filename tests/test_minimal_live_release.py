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
        self.assertIn("WSM_LIVE_PROFILE=systems/live-minimal.scm sh ./scripts/build_iso.sh", makefile)

    def test_profile_has_a_dedicated_unprivileged_console_login(self) -> None:
        profile = (ROOT / "systems" / "live-minimal.scm").read_text(encoding="utf-8")
        self.assertIn('(auto-login "wsm")', profile)
        self.assertIn('(mingetty-configuration-tty config) "tty2"', profile)
        self.assertIn("wpa-supplicant-service-type", profile)
        self.assertNotIn("plasma-desktop-service-type", profile)

    def test_guix_package_installs_python_runtime_and_wsm_commands(self) -> None:
        package = (ROOT / "wsm" / "packages" / "wsm.scm").read_text(encoding="utf-8")
        self.assertIn("(guix utils)", package)
        self.assertIn("(version-major+minor", package)
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
        normalized_builder = " ".join(builder.split())
        self.assertIn(
            'guix time-machine -C "$LOCK" -L "$ROOT" -- system -L "$ROOT" image',
            normalized_builder,
        )
        self.assertIn(
            'guix time-machine -C "$LOCK" -L "$ROOT" -- describe -f channels',
            normalized_builder,
        )
        self.assertNotIn('guix time-machine -C "$LOCK" -- -L "$ROOT"', normalized_builder)
        self.assertIn(
            '"guix", "time-machine", "-C", str(lock), "-L", str(repo_root), "--", '
            '"system", "-L", str(repo_root), "image"',
            normalized_builder,
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
        self.assertIn("$(MAKE) check-compatibility-eval", evaluation)
        compatibility = makefile.split("check-compatibility-eval:", 1)[1].split("\n\n", 1)[0]
        self.assertIn(
            "-C channels/compatibility.lock.scm -L . -- system -L . build systems/live-compat.scm --dry-run",
            compatibility,
        )
        self.assertIn("(gnu system locale)", (ROOT / "systems" / "live-minimal.scm").read_text(encoding="utf-8"))

    def test_boot_smoke_diagnostics_are_visible_and_saved_on_failure(self) -> None:
        workflow = (ROOT / ".github/workflows/release-minimal-live.yml").read_text(encoding="utf-8")
        bios = workflow.index("name: BIOS boot acceptance")
        uefi = workflow.index("name: UEFI boot acceptance")
        diagnostics = workflow.index("name: Зберегти діагностику boot smoke")
        manifest = workflow.index("name: Маніфест і контрольні суми")
        self.assertLess(bios, uefi)
        self.assertLess(uefi, diagnostics)
        self.assertLess(diagnostics, manifest)
        self.assertIn('| tee "$release_dist/boot-bios.json"', workflow)
        self.assertIn('| tee "$release_dist/boot-uefi.json"', workflow)
        section = workflow[diagnostics:manifest]
        self.assertIn("if: always()", section)
        self.assertIn("actions/upload-artifact@v7", section)
        self.assertIn("boot-bios.json", section)
        self.assertIn("boot-uefi.json", section)
        self.assertIn("if-no-files-found: ignore", section)
        self.assertIn("retention-days: 7", section)

    def test_minimal_live_marker_is_routed_to_serial_console(self) -> None:
        profile = (ROOT / "systems/live-minimal.scm").read_text(encoding="utf-8")
        self.assertIn('(call-with-output-file "/dev/console"', profile)
        self.assertIn(
            '(kernel-arguments ' + "'" + '("console=tty1" "console=ttyS0,115200"))',
            profile,
        )
        self.assertNotIn(
            '(kernel-arguments ' + "'" + '("console=ttyS0,115200" "console=tty1"))',
            profile,
        )

    def test_release_workflow_uses_current_node24_actions(self) -> None:
        workflow = (ROOT / ".github/workflows/release-minimal-live.yml").read_text(encoding="utf-8")
        self.assertIn("actions/checkout@v7", workflow)
        self.assertIn("actions/setup-python@v7", workflow)
        self.assertIn("actions/upload-artifact@v7", workflow)
        self.assertNotIn("actions/checkout@v4", workflow)
        self.assertNotIn("actions/setup-python@v5", workflow)

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


    def test_release_assets_are_verified_before_draft_publication(self) -> None:
        workflow = (ROOT / ".github/workflows/release-minimal-live.yml").read_text(encoding="utf-8")
        create_step = workflow.index("name: Створити чернетку релізу та завантажити assets")
        verify_step = workflow.index("name: Перевірити завантажені assets до публікації")
        publish_step = workflow.index("name: Опублікувати перевірений GitHub pre-release")
        cleanup = workflow.index("gh release delete-asset")
        upload = workflow.index("gh release upload")
        download = workflow.index("gh release download")
        verify = workflow.index("scripts/verify_release_assets.py")
        publish = workflow.index("gh release edit")
        self.assertLess(create_step, verify_step)
        self.assertLess(verify_step, publish_step)
        self.assertLess(cleanup, upload)
        self.assertLess(upload, download)
        self.assertLess(download, verify)
        self.assertLess(verify, publish)
        self.assertIn("--draft --prerelease", workflow)
        self.assertIn("--draft=false", workflow)
        self.assertIn('RELEASE_EXISTS=true', workflow)
        self.assertIn('[ "$TARGET_COMMIT" != "$GITHUB_SHA" ]', workflow)
        self.assertIn('[ "$IS_DRAFT" != "true" ]', workflow)
        self.assertIn("--json assets --jq '.assets[].name'", workflow)
        self.assertIn("Повідомити причину збою", workflow)

    def test_release_manifest_heredoc_closes_before_asset_upload_steps(self) -> None:
        workflow = (ROOT / ".github/workflows/release-minimal-live.yml").read_text(encoding="utf-8")
        manifest_start = workflow.index("name: Маніфест і контрольні суми")
        draft_start = workflow.index("name: Створити чернетку релізу та завантажити assets")
        manifest_step = workflow[manifest_start:draft_start]
        self.assertIn('build_manifest_sha256":sha(bp)', manifest_step)
        self.assertIn('(root/"release-manifest.json").write_text', manifest_step)
        self.assertIn('(root/"SHA256SUMS").write_text', manifest_step)
        self.assertIn("\n          PY\n", manifest_step)
        self.assertIn('sha256sum -c SHA256SUMS', manifest_step)

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

class FailureReporterTests(unittest.TestCase):
    """When a step fails, the reason must end up where it can be read.

    Job logs need authentication this project's tools do not have. The commit
    comment is the only channel that survives, so the reporter must not depend
    on knowing in advance which step failed.
    """

    def test_reporter_dumps_every_log_in_the_build_directory(self) -> None:
        text = (ROOT / ".github/workflows/release-minimal-live.yml").read_text(encoding="utf-8")
        self.assertIn('"$RUNNER_TEMP"/wsm-live-build/*.log', text)
        self.assertIn('"$RUNNER_TEMP"/wsm-live-dist/*.json', text)

    def test_reporter_lists_the_build_directory(self) -> None:
        """A step can fail before writing any log at all."""
        text = (ROOT / ".github/workflows/release-minimal-live.yml").read_text(encoding="utf-8")
        self.assertIn("ls -la", text)

    def test_reporter_posts_a_commit_comment(self) -> None:
        text = (ROOT / ".github/workflows/release-minimal-live.yml").read_text(encoding="utf-8")
        self.assertIn("/commits/$GITHUB_SHA/comments", text)
        self.assertIn("if: failure()", text)

class SplitAssetTests(unittest.TestCase):
    """A Guix closure does not fit one GitHub asset, and refusing means never shipping."""

    def setUp(self) -> None:
        self.text = (ROOT / ".github/workflows/release-minimal-live.yml").read_text(encoding="utf-8")

    def test_split_runs_after_acceptance_and_manifest(self) -> None:
        """Acceptance boots the image; it must exist as one file when it runs."""
        split = self.text.index("Поділити образ на частини")
        self.assertGreater(split, self.text.index("BIOS boot acceptance"))
        self.assertGreater(split, self.text.index("UEFI boot acceptance"))
        self.assertGreater(split, self.text.index("Маніфест і контрольні суми"))

    def test_split_happens_before_the_upload(self) -> None:
        self.assertLess(
            self.text.index("Поділити образ на частини"),
            self.text.index("Створити чернетку релізу"),
        )

    def test_parts_are_listed_as_assets(self) -> None:
        self.assertIn('"$release_dist/$release_iso".part*', self.text)

    def test_whole_step_output_is_captured(self) -> None:
        """The refusal used to print to the job log, which needs authentication."""
        self.assertIn('exec > >(tee -a "$WSM_ISO_DIR/step.log")', self.text)

    def test_iso_size_is_reported_before_any_decision(self) -> None:
        self.assertIn("ISO size:", self.text)

class SplitChecksumTests(unittest.TestCase):
    """After a split, the manifests must describe what is actually published."""

    def setUp(self) -> None:
        self.text = (ROOT / ".github/workflows/release-minimal-live.yml").read_text(encoding="utf-8")

    def test_checksums_are_rewritten_after_the_split(self) -> None:
        split = self.text.index("Поділити образ на частини")
        rewrite = self.text.index("checksums rewritten for", split)
        self.assertGreater(rewrite, split)

    def test_manifest_records_parts(self) -> None:
        self.assertIn('artifact["published_as"] = "parts"', self.text)
        self.assertIn('artifact["parts"] = parts', self.text)

    def test_sha256sums_covers_the_parts_not_the_removed_image(self) -> None:
        """The read-back check rejects a listed file that is not in the upload."""
        self.assertIn("covered = [root / name for name in parts]", self.text)
        self.assertIn("if not split:", self.text)



if __name__ == "__main__":
    unittest.main()
