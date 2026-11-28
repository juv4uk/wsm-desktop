# SPDX-License-Identifier: LicenseRef-Volnist
"""Safety and command-construction tests for the disposable QEMU harness."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install.tool_closure import (
    LINE_PREFIX,
    PROTOCOL_VERSION,
    STATE_NOT_EXECUTABLE,
    STATE_OK,
    STATE_UNRESOLVED,
    SUMMARY_PREFIX,
    inspect,
    parse,
    render,
    tool_state,
)
from wsm_install.tool_map import TOOLS
from scripts.qemu_boot_smoke import (
    EXIT_BOOT_NOT_CONFIRMED,
    EXIT_TOOL_CLOSURE_FAILED,
    MAX_CPUS,
    MAX_DISK_MIB,
    MAX_MEMORY_MIB,
    MAX_TIMEOUT_SECONDS,
    MIN_CPUS,
    MIN_DISK_MIB,
    MIN_MEMORY_MIB,
    MIN_TIMEOUT_SECONDS,
    BoundedProcessResult,
    MAX_BOOT_MARKER_BYTES,
    MAX_SERIAL_CAPTURE_BYTES,
    MAX_STDERR_CAPTURE_BYTES,
    build_qemu_command,
    main,
    sha256_of,
    parse_disk_size_mib,
    run_bounded_process,
    validate_iso,
    validate_limits,
)


class QemuBootSmokeTests(unittest.TestCase):
    def test_default_capture_limits_are_explicit(self) -> None:
        self.assertEqual(MAX_SERIAL_CAPTURE_BYTES, 1024 * 1024)
        self.assertEqual(MAX_STDERR_CAPTURE_BYTES, 256 * 1024)
        self.assertLessEqual(MAX_BOOT_MARKER_BYTES, 1024)

    def test_command_uses_json_for_paths_and_disables_host_io_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            iso = root / "live.iso"
            qcow2 = root / "tmp,comma" / "disk.qcow2"
            serial = root / "tmp,comma" / "serial.log"
            iso.write_bytes(b"synthetic ISO placeholder")
            command = build_qemu_command("qemu-system-x86_64", iso, qcow2, 2048, 2)

            blockdev_args = [
                json.loads(command[index + 1])
                for index, item in enumerate(command[:-1])
                if item == "-blockdev"
            ]

            self.assertEqual(blockdev_args[0]["filename"], str(qcow2))
            self.assertEqual(blockdev_args[1]["file"], "wsm-disk-file")
            self.assertEqual(command[command.index("-serial") + 1], "stdio")
            self.assertNotIn("-chardev", command)
            self.assertIn("-nic", command)
            self.assertEqual(command[command.index("-nic") + 1], "none")
            self.assertIn("accel=tcg", " ".join(command))
            self.assertNotIn("/dev/sd", " ".join(command))
            self.assertNotIn("/dev/nvme", " ".join(command))
            self.assertNotIn("host=", " ".join(command))
            self.assertFalse(any("pflash" in item or "efi" in item.lower() for item in command))

    def test_comma_in_temporary_root_is_preserved_in_json_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            comma_root = Path(parent) / "tmp,comma"
            comma_root.mkdir()
            iso = Path(parent) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")
            real_tempdir = tempfile.TemporaryDirectory

            with patch(
                "scripts.qemu_boot_smoke.tempfile.TemporaryDirectory",
                side_effect=lambda prefix: real_tempdir(prefix=prefix, dir=comma_root),
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    result = main(["--iso", str(iso), "--dry-run"])
            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            command = payload["qemu_command"]
            blockdev = [
                json.loads(command[index + 1])
                for index, item in enumerate(command[:-1])
                if item == "-blockdev"
            ]
            self.assertIn("tmp,comma", blockdev[0]["filename"])
            self.assertEqual(command[command.index("-serial") + 1], "stdio")
            self.assertNotIn("tmp,comma", command)

    def test_resource_limits_accept_all_documented_edges(self) -> None:
        validate_limits(MIN_TIMEOUT_SECONDS, MIN_MEMORY_MIB, MIN_CPUS, f"{MIN_DISK_MIB}M")
        validate_limits(MAX_TIMEOUT_SECONDS, MAX_MEMORY_MIB, MAX_CPUS, f"{MAX_DISK_MIB // 1024}G")

    def test_resource_limits_reject_values_outside_each_edge(self) -> None:
        invalid_cases = [
            (MIN_TIMEOUT_SECONDS - 1, 2048, 2, "4G"),
            (MAX_TIMEOUT_SECONDS + 1, 2048, 2, "4G"),
            (120, MIN_MEMORY_MIB - 1, 2, "4G"),
            (120, MAX_MEMORY_MIB + 1, 2, "4G"),
            (120, 2048, MIN_CPUS - 1, "4G"),
            (120, 2048, MAX_CPUS + 1, "4G"),
            (120, 2048, 2, f"{MIN_DISK_MIB - 1}M"),
            (120, 2048, 2, f"{MAX_DISK_MIB // 1024 + 1}G"),
            (120, 2048, 2, "1T"),
        ]
        for values in invalid_cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    validate_limits(*values)

    def test_parse_disk_size_supports_equivalent_units(self) -> None:
        self.assertEqual(parse_disk_size_mib("1G"), 1024)
        self.assertEqual(parse_disk_size_mib("1024M"), 1024)
        self.assertEqual(parse_disk_size_mib("64G"), MAX_DISK_MIB)

    def test_validate_iso_rejects_directory_and_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                validate_iso(root)
            empty = root / "empty.iso"
            empty.touch()
            with self.assertRaises(ValueError):
                validate_iso(empty)

    def test_validate_iso_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "image.iso"
            target.write_bytes(b"iso")
            link = root / "link.iso"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                validate_iso(link)

    def test_dry_run_reports_no_passthrough_or_guest_installer_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(["--iso", str(iso), "--dry-run"])
            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["mode"], "dry-run")
            self.assertFalse(payload["host_device_passthrough"])
            self.assertFalse(payload["network_enabled"])
            self.assertFalse(payload["efi_variable_store"])
            self.assertFalse(payload["guest_installer_execution"])
            self.assertIn("disposable.qcow2", payload["qcow2_path"])

    def test_invalid_resource_request_fails_before_qemu(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")
            with patch("scripts.qemu_boot_smoke.subprocess.run") as run:
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result = main(["--iso", str(iso), "--memory-mib", str(MAX_MEMORY_MIB + 1)])
            self.assertEqual(result, 2)
            run.assert_not_called()
            self.assertIn("memory must be between", stderr.getvalue())

    def test_runtime_confirms_only_explicit_serial_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")
            calls = []

            def fake_run(command, **kwargs):
                calls.append(command)
                Path(command[4]).touch()
                return subprocess.CompletedProcess(command, 0, "", "")

            captured = BoundedProcessResult(
                returncode=None,
                timed_out=True,
                stdout_tail=b"booting\nWSM-LIVE-READY\n",
                stderr_tail=b"bounded warning",
                stdout_bytes_seen=24,
                stderr_bytes_seen=15,
                stdout_truncated=False,
                stderr_truncated=False,
                marker_seen=True,
            )
            stdout = io.StringIO()
            with patch("scripts.qemu_boot_smoke.shutil.which", side_effect=lambda name: name), patch(
                "scripts.qemu_boot_smoke.subprocess.run", side_effect=fake_run
            ), patch("scripts.qemu_boot_smoke.run_bounded_process", return_value=captured) as runner, contextlib.redirect_stdout(stdout):
                result = main(["--iso", str(iso), "--boot-marker", "WSM-LIVE-READY"])
            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["iso_sha256"], sha256_of(iso))
            self.assertTrue(payload["boot_confirmed"])
            self.assertTrue(payload["qemu_timed_out"])
            self.assertEqual(payload["serial_output_tail"], "booting\nWSM-LIVE-READY\n")
            self.assertEqual(payload["qemu_error"], "bounded warning")
            self.assertFalse(payload["serial_truncated"])
            self.assertFalse(payload["stderr_truncated"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1:4], ["create", "-f", "qcow2"])
            runner.assert_called_once()
            self.assertEqual(runner.call_args.kwargs["marker"], "WSM-LIVE-READY")

    def test_bounded_capture_detects_marker_before_retained_tail(self) -> None:
        marker = "WSM_MARKER_AT_STREAM_START"
        child = (
            "import sys\n"
            f"sys.stdout.buffer.write({marker.encode()!r} + b'S' * 200000)\n"
            "sys.stdout.flush()\n"
            "sys.stderr.buffer.write(b'E' * 100000)\n"
            "sys.stderr.flush()\n"
        )
        result = run_bounded_process(
            [sys.executable, "-c", child],
            timeout_seconds=5,
            marker=marker,
            max_stdout_bytes=1024,
            max_stderr_bytes=512,
            read_chunk_bytes=257,
        )
        self.assertFalse(result.timed_out)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.marker_seen)
        self.assertTrue(result.stdout_truncated)
        self.assertTrue(result.stderr_truncated)
        self.assertEqual(len(result.stdout_tail), 1024)
        self.assertEqual(len(result.stderr_tail), 512)
        self.assertGreater(result.stdout_bytes_seen, 200000)
        self.assertEqual(result.stderr_bytes_seen, 100000)
        self.assertNotIn(marker.encode(), result.stdout_tail)

    def test_bounded_capture_detects_marker_split_across_reads(self) -> None:
        marker = "SPLIT-MARKER-BOUNDARY"
        child = (
            "import os, sys, time\n"
            "os.write(1, b'prefix-SPLIT-')\n"
            "time.sleep(0.05)\n"
            "os.write(1, b'MARKER-BOUNDARY-suffix')\n"
        )
        result = run_bounded_process(
            [sys.executable, "-c", child],
            timeout_seconds=5,
            marker=marker,
            max_stdout_bytes=8,
            max_stderr_bytes=8,
            read_chunk_bytes=3,
        )
        self.assertTrue(result.marker_seen)
        self.assertTrue(result.stdout_truncated)
        self.assertLessEqual(len(result.stdout_tail), 8)

    def test_bounded_capture_kills_noisy_child_after_timeout(self) -> None:
        child = (
            "import os, time\n"
            "chunk = b'X' * 8192\n"
            "while True:\n"
            "    os.write(1, chunk)\n"
            "    os.write(2, chunk)\n"
        )
        result = run_bounded_process(
            [sys.executable, "-c", child],
            timeout_seconds=0.2,
            marker="NEVER-SEEN",
            max_stdout_bytes=2048,
            max_stderr_bytes=1024,
            read_chunk_bytes=512,
        )
        self.assertTrue(result.timed_out)
        self.assertTrue(result.stdout_truncated)
        self.assertTrue(result.stderr_truncated)
        self.assertLessEqual(len(result.stdout_tail), 2048)
        self.assertLessEqual(len(result.stderr_tail), 1024)
        self.assertGreater(result.stdout_bytes_seen, 2048)
        self.assertGreater(result.stderr_bytes_seen, 1024)
        self.assertFalse(result.marker_seen)

    def test_oversized_boot_marker_is_rejected_before_qemu(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch("scripts.qemu_boot_smoke.subprocess.run") as run, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = main([
                    "--iso", str(iso),
                    "--boot-marker", "M" * (MAX_BOOT_MARKER_BYTES + 1),
                ])
            self.assertEqual(result, 2)
            run.assert_not_called()
            self.assertIn("boot marker must be no more than", stderr.getvalue())

    @unittest.skipUnless(
        shutil.which("qemu-system-x86_64") and shutil.which("qemu-img"),
        "real QEMU CLI smoke requires qemu-system-x86_64 and qemu-img",
    )
    def test_real_qemu_accepts_generated_command_with_comma_path(self) -> None:
        """Start QEMU paused to validate real CLI parsing without booting a guest."""
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent) / "tmp,comma"
            root.mkdir()
            iso = root / "synthetic.iso"
            qcow2 = root / "disposable.qcow2"
            iso.write_bytes(b"\\0" * 2048)
            subprocess.run(
                ["qemu-img", "create", "-f", "qcow2", str(qcow2), "256M"],
                check=True,
                capture_output=True,
                text=True,
            )

            command = build_qemu_command(
                "qemu-system-x86_64", iso, qcow2, 256, 1
            )
            # Pause the guest CPU so this test validates device/option setup only.
            command.insert(1, "-S")
            try:
                subprocess.run(
                    command,
                    check=False,
                    timeout=3,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except subprocess.TimeoutExpired:
                return
            self.fail("QEMU exited before the bounded paused-VM smoke timeout")


PROFILE = "/run/current-system/profile/bin"


def closure_lines(states: dict[str, str] | None = None, profile: str = PROFILE) -> str:
    """A synthetic guest report, exactly as the probe would print it."""
    chosen = states or {}
    lines = []
    for name in sorted(TOOLS):
        state = chosen.get(name, STATE_OK)
        lines.append(
            "|".join((LINE_PREFIX, PROTOCOL_VERSION, name, f"{profile}/{name}", state))
        )
    usable = sum(1 for name in TOOLS if chosen.get(name, STATE_OK) == STATE_OK)
    verdict = "ok" if usable == len(TOOLS) else "fail"
    lines.append("|".join((SUMMARY_PREFIX, PROTOCOL_VERSION, verdict, f"{usable}/{len(TOOLS)}")))
    return "\n".join(lines) + "\n"


def make_root(
    root: Path,
    *,
    absent: tuple[str, ...] = (),
    nonexec: tuple[str, ...] = (),
    profile: str = PROFILE,
) -> None:
    """A throwaway Guix-shaped root: no /usr, tools only in the profile."""
    for name in TOOLS:
        if name in absent:
            continue
        target = root / profile.lstrip("/") / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/bin/sh\n", encoding="utf-8")
        target.chmod(0o644 if name in nonexec else 0o755)


class GuestReportParsingTests(unittest.TestCase):
    """What the guest said, read on the host: no QEMU, no image."""

    def test_a_complete_report_is_a_pass(self) -> None:
        verdict = parse(closure_lines())
        self.assertEqual(verdict.status, "pass")
        self.assertEqual(verdict.reported_lines, len(TOOLS))
        self.assertEqual(verdict.missing, ())
        self.assertEqual(verdict.not_executable, ())
        self.assertEqual(verdict.problems, ())

    def test_a_missing_summary_is_a_failure(self) -> None:
        report = "\n".join(
            line for line in closure_lines().splitlines()
            if not line.startswith(SUMMARY_PREFIX)
        )
        verdict = parse(report)
        self.assertEqual(verdict.status, "fail")
        self.assertTrue(any("summary" in problem for problem in verdict.problems))

    def test_a_duplicate_summary_is_a_failure(self) -> None:
        report = closure_lines() + closure_lines().splitlines()[-1] + "\n"
        verdict = parse(report)
        self.assertEqual(verdict.status, "fail")
        self.assertTrue(any("more than once" in problem for problem in verdict.problems))

    def test_a_malformed_summary_count_is_a_failure(self) -> None:
        report = closure_lines().replace(
            f"{SUMMARY_PREFIX}|{PROTOCOL_VERSION}|ok|",
            f"{SUMMARY_PREFIX}|{PROTOCOL_VERSION}|ok|",
        ).replace("|7/7", "|7/not-a-number")
        verdict = parse(report)
        self.assertEqual(verdict.status, "fail")
        self.assertTrue(any("malformed summary" in problem for problem in verdict.problems))

    def test_a_summary_total_must_match_the_expected_tool_count(self) -> None:
        report = closure_lines().replace("|7/7", "|7/8")
        verdict = parse(report)
        self.assertEqual(verdict.status, "fail")
        self.assertTrue(any("total" in problem for problem in verdict.problems))

    def test_summary_counts_and_verdict_must_match_tool_rows(self) -> None:
        all_ok_but_fail_summary = closure_lines().replace("|ok|7/7", "|fail|0/7")
        verdict = parse(all_ok_but_fail_summary)
        self.assertEqual(verdict.status, "fail")
        self.assertTrue(any("usable count" in problem for problem in verdict.problems))
        self.assertTrue(any("summary verdict" in problem for problem in verdict.problems))

        non_ok_rows_but_pass_summary = closure_lines({"mount": STATE_NOT_EXECUTABLE}).replace(
            "|fail|6/7", "|ok|7/7"
        )
        verdict = parse(non_ok_rows_but_pass_summary)
        self.assertEqual(verdict.status, "fail")
        self.assertTrue(any("summary verdict" in problem for problem in verdict.problems))

    def test_ok_rows_require_an_absolute_path_under_a_guix_profile_prefix(self) -> None:
        original = f"|sgdisk|{PROFILE}/sgdisk|ok"
        invalid_paths = (
            "-",
            "sgdisk",
            "/tmp/sgdisk",
            "/usr/sbin/sgdisk",
            "/run/current-system/profile/bin/not-sgdisk",
        )
        for path in invalid_paths:
            with self.subTest(path=path):
                report = closure_lines().replace(original, f"|sgdisk|{path}|ok")
                verdict = parse(report)
                self.assertEqual(verdict.status, "fail")
                self.assertTrue(
                    any("requires an absolute" in problem for problem in verdict.problems),
                    verdict.problems,
                )

    def test_unresolved_rows_must_not_claim_a_path(self) -> None:
        report = closure_lines({"sgdisk": STATE_UNRESOLVED})
        verdict = parse(report)
        self.assertEqual(verdict.status, "fail")
        self.assertTrue(
            any("unresolved state must use '-'" in problem for problem in verdict.problems),
            verdict.problems,
        )

    def test_a_missing_tool_is_a_failure_that_names_it(self) -> None:
        text = "\n".join(
            line for line in closure_lines().splitlines() if "|sgdisk|" not in line
        )
        verdict = parse(text)
        self.assertEqual(verdict.status, "fail")
        self.assertEqual(verdict.missing, ("sgdisk",))
        self.assertTrue(
            any("sgdisk" in problem for problem in verdict.problems),
            verdict.problems,
        )

    def test_a_non_executable_tool_is_a_failure_and_is_named_separately(self) -> None:
        verdict = parse(closure_lines({"mount": STATE_NOT_EXECUTABLE}))
        self.assertEqual(verdict.status, "fail")
        self.assertEqual(verdict.not_executable, ("mount",))
        self.assertEqual(verdict.missing, ())

    def test_an_empty_report_is_a_failure_not_an_empty_pass(self) -> None:
        """Silence proves nothing; a pass would be the worst possible reading."""
        verdict = parse("")
        self.assertEqual(verdict.status, "fail")
        self.assertEqual(verdict.reported_lines, 0)
        self.assertEqual(verdict.missing, tuple(sorted(TOOLS)))

    def test_a_shorter_report_cannot_stand_in_for_the_full_set(self) -> None:
        """A guest that checks six tools has not checked the seventh."""
        text = "\n".join(
            line for line in closure_lines().splitlines() if "|mkfs.fat|" not in line
        )
        verdict = parse(text)
        self.assertEqual(verdict.status, "fail")
        self.assertEqual(verdict.missing, ("mkfs.fat",))

    def test_an_unknown_tool_does_not_replace_a_missing_one(self) -> None:
        text = closure_lines() + f"{LINE_PREFIX}|{PROTOCOL_VERSION}|toytool|/bin/toytool|ok\n"
        verdict = parse(text)
        self.assertEqual(verdict.status, "fail")
        self.assertTrue(any("toytool" in problem for problem in verdict.problems))
        self.assertNotIn("toytool", verdict.reported)

    def test_a_duplicated_tool_is_refused(self) -> None:
        verdict = parse(closure_lines() + closure_lines())
        self.assertEqual(verdict.status, "fail")
        self.assertTrue(any("more than once" in problem for problem in verdict.problems))

    def test_a_truncated_line_fails_instead_of_being_skipped(self) -> None:
        verdict = parse(closure_lines() + f"{LINE_PREFIX}|{PROTOCOL_VERSION}|sgdisk\n")
        self.assertEqual(verdict.status, "fail")
        self.assertTrue(any("malformed" in problem for problem in verdict.problems))

    def test_the_report_is_found_inside_boot_noise(self) -> None:
        """The serial console carries kernel messages too."""
        text = (
            "[    3.210112] systemd[1]: Reached target Multi-User System.\n"
            "WSM_LIVE_READY\n"
            "WSM_INSTALLER_OK\n"
            + closure_lines()
            + "[    9.000000] random: crng init done\n"
        )
        verdict = parse(text)
        self.assertEqual(verdict.status, "pass")

    def test_the_protocol_round_trips_from_a_real_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_root(root)
            states = inspect(root, prefixes=(PROFILE,))
            self.assertEqual({state.state for state in states}, {STATE_OK})
            verdict = parse("\n".join(render(states)))
        self.assertEqual(verdict.status, "pass")
        self.assertEqual(verdict.reported_lines, len(TOOLS))


class ProbeSideTests(unittest.TestCase):
    """What the guest would say, decided on the host against a throwaway root."""

    def test_an_absent_tool_is_unresolved_and_the_verdict_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_root(root, absent=("sgdisk",))
            states = inspect(root, prefixes=(PROFILE,))
            verdict = parse("\n".join(render(states)))
        by_name = {state.name: state for state in states}
        self.assertEqual(by_name["sgdisk"].state, STATE_UNRESOLVED)
        self.assertEqual(by_name["sgdisk"].path, "")
        self.assertEqual(verdict.status, "fail")
        self.assertEqual(verdict.missing, ("sgdisk",))

    def test_a_non_executable_tool_is_reported_as_such_not_as_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_root(root, nonexec=("mount",))
            states = inspect(root, prefixes=(PROFILE,))
        by_name = {state.name: state for state in states}
        self.assertEqual(by_name["mount"].state, STATE_NOT_EXECUTABLE)
        self.assertIn("not executable", by_name["mount"].detail or "")

    def test_the_message_names_the_guix_package_that_owns_the_tool(self) -> None:
        """The fix for a missing path is a package in the closure, not a file."""
        with tempfile.TemporaryDirectory() as directory:
            state, detail = tool_state("sgdisk", Path(directory), "/usr/sbin/sgdisk")
        self.assertEqual(state, "missing")
        self.assertIn("gptfdisk", detail or "")

    def test_the_probe_never_runs_the_tools_it_checks(self) -> None:
        """Read-only means read-only: no exec, no mount, no block device."""
        source = (ROOT / "wsm_install" / "tool_closure.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.system", "shutil", "mount(", "mkfs"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


class ToolClosureEvidenceTests(unittest.TestCase):
    """The verdict has to land in the boot evidence and change the exit code."""

    def run_harness(self, serial: str, *extra: str):
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")

            def fake_run(command, **kwargs):
                Path(command[4]).touch()
                return subprocess.CompletedProcess(command, 0, "", "")

            captured = BoundedProcessResult(
                returncode=None,
                timed_out=True,
                stdout_tail=serial.encode("utf-8"),
                stderr_tail=b"",
                stdout_bytes_seen=len(serial),
                stderr_bytes_seen=0,
                stdout_truncated=False,
                stderr_truncated=False,
                marker_seen="WSM_LIVE_READY" in serial,
                second_marker_seen="WSM_INSTALLER_OK" in serial,
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch("scripts.qemu_boot_smoke.shutil.which", side_effect=lambda name: name), patch(
                "scripts.qemu_boot_smoke.subprocess.run", side_effect=fake_run
            ), patch("scripts.qemu_boot_smoke.run_bounded_process", return_value=captured), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(
                    [
                        "--iso", str(iso),
                        "--boot-marker", "WSM_LIVE_READY",
                        "--installer-marker", "WSM_INSTALLER_OK",
                        *extra,
                    ]
                )
        return code, stdout.getvalue(), stderr.getvalue()

    def test_a_passing_report_lands_in_the_evidence(self) -> None:
        serial = "WSM_LIVE_READY\nWSM_INSTALLER_OK\n" + closure_lines()
        code, out, _ = self.run_harness(serial, "--tool-closure-marker", "WSM_TOOL_CLOSURE")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        closure = payload["tool_closure"]
        self.assertEqual(closure["status"], "pass")
        self.assertEqual(closure["marker"], "WSM_TOOL_CLOSURE")
        self.assertTrue(closure["guest_reported"])
        self.assertEqual(sorted(closure["reported"]), sorted(TOOLS))
        self.assertEqual(closure["reported"]["sgdisk"]["path"], f"{PROFILE}/sgdisk")

    def test_a_missing_tool_fails_the_boot_acceptance(self) -> None:
        serial = "WSM_LIVE_READY\nWSM_INSTALLER_OK\n" + "\n".join(
            line for line in closure_lines().splitlines() if "|sgdisk|" not in line
        )
        code, out, err = self.run_harness(serial, "--tool-closure-marker", "WSM_TOOL_CLOSURE")
        self.assertEqual(code, EXIT_TOOL_CLOSURE_FAILED)
        payload = json.loads(out)
        self.assertTrue(payload["boot_confirmed"])
        self.assertEqual(payload["tool_closure"]["status"], "fail")
        self.assertEqual(payload["tool_closure"]["missing"], ["sgdisk"])
        self.assertIn("sgdisk", err)

    def test_a_non_executable_tool_fails_the_boot_acceptance(self) -> None:
        serial = "WSM_LIVE_READY\n" + closure_lines({"mount": STATE_NOT_EXECUTABLE})
        code, out, _ = self.run_harness(serial, "--tool-closure-marker", "WSM_TOOL_CLOSURE")
        self.assertEqual(code, EXIT_TOOL_CLOSURE_FAILED)
        payload = json.loads(out)
        self.assertEqual(payload["tool_closure"]["not_executable"], ["mount"])

    def test_silence_from_the_guest_fails_rather_than_passes(self) -> None:
        """A guest that never reported has proved nothing about its tools."""
        code, out, err = self.run_harness(
            "WSM_LIVE_READY\nWSM_INSTALLER_OK\n", "--tool-closure-marker", "WSM_TOOL_CLOSURE"
        )
        self.assertEqual(code, EXIT_TOOL_CLOSURE_FAILED)
        payload = json.loads(out)
        self.assertEqual(payload["tool_closure"]["status"], "fail")
        self.assertFalse(payload["tool_closure"]["guest_reported"])
        self.assertEqual(payload["tool_closure"]["reported_lines"], 0)
        self.assertIn("did not prove", err)

    def test_boot_not_confirmed_still_wins_over_the_closure_verdict(self) -> None:
        code, _, _ = self.run_harness(
            closure_lines(), "--tool-closure-marker", "WSM_TOOL_CLOSURE"
        )
        self.assertEqual(code, EXIT_BOOT_NOT_CONFIRMED)

    def test_an_unasked_check_claims_nothing(self) -> None:
        code, out, err = self.run_harness("WSM_LIVE_READY\n" + closure_lines())
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["tool_closure"]["status"], "not-checked")
        self.assertIsNone(payload["tool_closure"]["marker"])
        self.assertEqual(payload["tool_closure"]["reported"], {})
        self.assertIn("NOTE", err)

    def test_the_dry_run_does_not_claim_a_closure_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(
                    ["--iso", str(iso), "--dry-run", "--tool-closure-marker", "WSM_TOOL_CLOSURE"]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["tool_closure"]["status"], "not-checked")
        self.assertEqual(payload["tool_closure"]["marker"], "WSM_TOOL_CLOSURE")


class ToolClosureWiringTests(unittest.TestCase):
    """The image has to run the probe, and the release has to require the verdict."""

    def setUp(self) -> None:
        self.profile = (ROOT / "systems" / "live-minimal.scm").read_text(encoding="utf-8")
        self.workflow = (
            ROOT / ".github" / "workflows" / "release-minimal-live.yml"
        ).read_text(encoding="utf-8")
        self.cli = (ROOT / "wsm_install" / "cli.py").read_text(encoding="utf-8")
        self.tool_paths = (ROOT / "wsm_install" / "tools.py").read_text(encoding="utf-8")

    def test_the_image_runs_the_probe_from_its_own_profile(self) -> None:
        self.assertIn("wsm_install.tool_closure", self.profile)
        self.assertIn('"--console" "/dev/console"', self.profile)
        self.assertIn("/run/current-system/profile/bin/python3", self.profile)

    def test_the_planner_and_guest_probe_share_guix_profile_prefixes(self) -> None:
        self.assertIn("GUIX_PROFILE_PREFIXES", self.tool_paths)
        self.assertIn("tool_prefixes=_tool_prefixes_for_running_system()", self.cli)
        self.assertIn('"/run/current-system/profile/bin"', self.profile)
        self.assertIn('"/run/current-system/profile/sbin"', self.profile)

    def test_the_read_only_probe_does_not_mutate_the_shared_path(self) -> None:
        section = self.profile[
            self.profile.index("wsm-tool-closure-probe") : self.profile.index("(operating-system")
        ]
        self.assertNotIn('setenv "PATH"', section)

    def test_the_probe_runs_after_the_live_and_installer_markers(self) -> None:
        """A tool report before the system is up would describe something else."""
        self.assertIn(
            "(requirement '(wsm-live-ready wsm-installer-selfcheck))", self.profile
        )

    def test_the_service_is_registered(self) -> None:
        self.assertIn("wsm-tool-closure-probe", self.profile)
        self.assertIn("(provision '(wsm-tool-closure))", self.profile)

    def test_a_probe_failure_cannot_break_boot(self) -> None:
        section = self.profile[
            self.profile.index("wsm-tool-closure-probe") : self.profile.index("(operating-system")
        ]
        self.assertIn("(catch #t", section)

    def test_the_probe_does_not_partition_format_or_mount(self) -> None:
        section = self.profile[
            self.profile.index("wsm-tool-closure-probe") : self.profile.index("(operating-system")
        ]
        for forbidden in ("mkfs", "sgdisk", "mount ", "guix system init"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, section)

    def test_both_firmware_boots_ask_for_the_closure_report(self) -> None:
        self.assertEqual(
            self.workflow.count("--tool-closure-marker WSM_TOOL_CLOSURE"), 2
        )

    def test_the_release_refuses_a_boot_without_a_passing_closure(self) -> None:
        self.assertIn('closure.get("status") != "pass"', self.workflow)
        self.assertIn("did not prove the installer tools exist", self.workflow)
        self.assertIn('"tool_closure":"pass"', self.workflow)


if __name__ == "__main__":
    unittest.main()
