# SPDX-License-Identifier: LicenseRef-Volnist
"""Behavioral tests for the read-only systemd boot profile collector."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import collect_boot_profile as cli  # noqa: E402
import wsm_perf.boot as boot  # noqa: E402


def make_proc_root(root: Path, *, boot_id: str = "00000000-1111-2222-3333-444444444444") -> Path:
    (root / "sys/kernel/random").mkdir(parents=True)
    (root / "sys/kernel/random/boot_id").write_text(boot_id + "\n", encoding="utf-8")
    (root / "uptime").write_text("123.45 67.89\n", encoding="utf-8")
    return root


class BootCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.object(boot, "collect_report", return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)

    def successful_runner(self, calls: list[tuple[list[str], dict[str, object]]]):
        def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((argv, kwargs))
            if argv[-1] == "--version":
                output = "systemd 262 (262.1)\n"
            elif argv[-1] == "time":
                output = (
                    "Startup finished in 1.0s (kernel) + 2.0s (initrd) + "
                    "3.0s (userspace) = 6.0s\n"
                    "multi-user.target reached after 2.9s in userspace\n"
                )
            elif argv[-1] == "blame":
                output = "1.234s example.service\n"
            else:
                output = "graphical.target @6.0s\n└─example.service @4.0s +2.0s\n"
            return subprocess.CompletedProcess(argv, 0, stdout=output, stderr="")

        return run

    def test_fixed_commands_capture_raw_outputs_without_shell(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []
        with tempfile.TemporaryDirectory() as directory:
            proc_root = make_proc_root(Path(directory))
            with patch.object(
                boot, "collect_report",
                return_value={
                    "environment": {"virtualization": "qemu"},
                    "collectors": [
                        {"name": "wsm-hwcheck-sysfs", "version": "0.2.0"}
                    ],
                },
            ):
                artifact = boot.collect_boot_profile(
                    proc_root=proc_root,
                    runner=self.successful_runner(calls),
                    which=lambda name: "/usr/bin/systemd-analyze",
                )

        self.assertEqual(len(calls), len(boot.COMMANDS))
        self.assertEqual(artifact["schema"], "wsm-boot-profile/1")
        self.assertEqual(artifact["collection_status"], "available")
        self.assertIn("multi-user.target reached", artifact["commands"]["time"]["stdout"])
        self.assertIn("example.service", artifact["commands"]["blame"]["stdout"])
        self.assertIn("graphical.target", artifact["commands"]["critical_chain_graphical"]["stdout"])
        self.assertEqual(artifact["environment"]["virtualization"]["detected"], "qemu")
        for argv, kwargs in calls:
            self.assertNotIn("shell", kwargs)
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertTrue(kwargs["capture_output"])
            self.assertEqual(kwargs["env"]["LC_ALL"], "C")
            self.assertLessEqual(kwargs["timeout"], boot.MAX_TIMEOUT_SECONDS)
            self.assertEqual(argv[0], "/usr/bin/systemd-analyze")

    def test_fixed_argv_allowlist_has_no_user_controlled_unit_or_shell(self) -> None:
        names = {name: args for name, args in boot.COMMANDS}
        self.assertEqual(names["time"], ("--no-pager", "time"))
        self.assertEqual(names["blame"], ("--no-pager", "blame"))
        self.assertEqual(
            names["critical_chain_default"],
            ("--no-pager", "critical-chain"),
        )
        self.assertEqual(
            names["critical_chain_graphical"],
            ("--no-pager", "critical-chain", "graphical.target"),
        )
        self.assertEqual(len(names), len(boot.COMMANDS))
        self.assertTrue(all(isinstance(arg, str) for args in names.values() for arg in args))

    def test_missing_systemd_analyze_is_unavailable_not_zero(self) -> None:
        runner = unittest.mock.Mock()
        artifact = boot.collect_boot_profile(
            runner=runner,
            which=lambda name: None,
        )
        self.assertEqual(artifact["collection_status"], "unavailable")
        self.assertTrue(
            all(
                command["status"] == "unavailable"
                and command["reason"] == "command-not-found"
                and command["exit_code"] is None
                for command in artifact["commands"].values()
            )
        )
        runner.assert_not_called()

    def test_timeout_is_recorded_with_partial_output(self) -> None:
        def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if argv[-1] == "time":
                raise subprocess.TimeoutExpired(
                    argv, kwargs["timeout"], output=b"Startup in progress", stderr=b"waiting"
                )
            return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

        artifact = boot.collect_boot_profile(
            runner=run,
            which=lambda name: "/usr/bin/systemd-analyze",
        )
        command = artifact["commands"]["time"]
        self.assertEqual(command["status"], "timeout")
        self.assertEqual(command["reason"], "command-timeout")
        self.assertIsNone(command["exit_code"])
        self.assertEqual(command["stdout"], "Startup in progress")
        self.assertEqual(command["stderr"], "waiting")
        self.assertNotEqual(artifact["collection_status"], "available")

    def test_nonzero_exit_is_not_pass(self) -> None:
        def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            code = 7 if argv[-1] == "blame" else 0
            return subprocess.CompletedProcess(argv, code, stdout="partial", stderr="denied")

        artifact = boot.collect_boot_profile(
            runner=run,
            which=lambda name: "/usr/bin/systemd-analyze",
        )
        self.assertEqual(artifact["commands"]["blame"]["status"], "failed")
        self.assertEqual(artifact["commands"]["blame"]["exit_code"], 7)
        self.assertEqual(artifact["commands"]["blame"]["reason"], "non-zero-exit")
        self.assertEqual(artifact["collection_status"], "partial")

    def test_command_output_is_bounded_and_truncation_is_explicit(self) -> None:
        payload = "x" * (boot.MAX_OUTPUT_BYTES + 1024)

        def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            output = payload if argv[-1] == "blame" else "ok"
            return subprocess.CompletedProcess(argv, 0, stdout=output, stderr=payload)

        artifact = boot.collect_boot_profile(
            runner=run,
            which=lambda name: "/usr/bin/systemd-analyze",
        )
        command = artifact["commands"]["blame"]
        self.assertLessEqual(len(command["stdout"].encode("utf-8")), boot.MAX_OUTPUT_BYTES)
        self.assertLessEqual(len(command["stderr"].encode("utf-8")), boot.MAX_OUTPUT_BYTES)
        self.assertTrue(command["stdout_truncated"])
        self.assertTrue(command["stderr_truncated"])

    def test_invalid_timeout_is_rejected_before_command_lookup(self) -> None:
        for timeout in (0, -1, float("inf"), float("nan"), boot.MAX_TIMEOUT_SECONDS + 1):
            with self.subTest(timeout=timeout):
                lookup = unittest.mock.Mock(return_value="/usr/bin/systemd-analyze")
                with self.assertRaises(ValueError):
                    boot.collect_boot_profile(timeout_seconds=timeout, which=lookup)
                lookup.assert_not_called()


class BootIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.object(boot, "collect_report", return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_boot_identity_uses_digest_not_raw_boot_uuid(self) -> None:
        raw_id = "00000000-1111-2222-3333-444444444444"
        with tempfile.TemporaryDirectory() as directory:
            proc_root = make_proc_root(Path(directory), boot_id=raw_id)
            identity = boot._boot_identity(proc_root)
            artifact = boot.collect_boot_profile(
                proc_root=proc_root,
                runner=unittest.mock.Mock(
                    side_effect=lambda argv, **kwargs: subprocess.CompletedProcess(
                        argv, 0, stdout="ok", stderr=""
                    )
                ),
                which=lambda name: "/usr/bin/systemd-analyze",
            )
        self.assertEqual(identity["status"], "available")
        self.assertEqual(
            identity["digest"],
            hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16],
        )
        self.assertNotIn(raw_id, json.dumps(artifact))
        self.assertEqual(artifact["uptime_seconds"], 123.45)

    def test_missing_or_malformed_procfs_is_unknown_not_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            proc_root = Path(directory)
            identity = boot._boot_identity(proc_root)
            uptime = boot._uptime_seconds(proc_root)
        self.assertEqual(identity["status"], "unknown")
        self.assertIsNone(identity["digest"])
        self.assertIsNone(uptime)

    def test_malformed_uptime_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            proc_root = Path(directory)
            (proc_root / "uptime").write_text("not-a-number 10\n", encoding="utf-8")
            self.assertIsNone(boot._uptime_seconds(proc_root))

    def test_unknown_virtualization_is_preserved(self) -> None:
        with patch.object(boot, "collect_report", return_value={}):
            evidence = boot._virtualization_evidence()
        self.assertEqual(evidence, {"detected": "unknown", "source": "unknown"})

    def test_profile_explains_systemd_timing_limits(self) -> None:
        with patch.object(boot, "collect_report", return_value={}):
            artifact = boot.collect_boot_profile(
                runner=unittest.mock.Mock(return_value=subprocess.CompletedProcess([], 0, "ok", "")),
                which=lambda name: "/usr/bin/systemd-analyze",
            )
        warnings = "\n".join(artifact["warnings"])
        self.assertIn("spawned", warnings)
        self.assertIn("parallel execution", warnings)
        self.assertIn("Firmware/loader timings", warnings)
        self.assertEqual(artifact["scope"], "system-boot")


class BootCliTests(unittest.TestCase):
    def test_cli_writes_json_artifact_to_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "boot-profile.json"
            artifact = {"schema": "wsm-boot-profile/1", "collection_status": "unavailable"}
            with patch.object(cli, "collect_boot_profile", return_value=artifact):
                result = cli.main(["--output", str(output), "--compact"])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), artifact)

    def test_cli_rejects_invalid_timeout_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "never-created.json"
            with patch.object(cli, "collect_boot_profile", side_effect=ValueError("bad timeout")):
                result = cli.main(["--timeout", "0", "--output", str(output)])
            self.assertEqual(result, 2)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
