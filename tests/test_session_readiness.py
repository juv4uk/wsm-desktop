# SPDX-License-Identifier: LicenseRef-Volnist
"""Behavior and privacy tests for the KDE Plasma session-readiness marker."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_perf import session  # noqa: E402

SCHEMA_PATH = ROOT / "schemas" / "desktop-session-readiness.schema.json"


class SessionReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = {
            "XDG_CURRENT_DESKTOP": "KDE",
            "XDG_SESSION_TYPE": "x11",
            "XDG_SESSION_ID": "8",
            "KDE_SESSION_VERSION": "6",
            "USER": "must-not-be-recorded",
        }
        self.runner = Mock(
            return_value=subprocess.CompletedProcess(
                ["loginctl"], 0,
                stdout="Id=8\nTimestampMonotonic=50000000\n",
                stderr="",
            )
        )

    def collect(self, **kwargs):
        return session.collect_session_readiness(
            environment=self.environment,
            proc_root=kwargs.pop("proc_root", Path("/missing-proc")),
            runner=kwargs.pop("runner", self.runner),
            which=kwargs.pop("which", lambda name: "/usr/bin/loginctl"),
            monotonic_ns=kwargs.pop("monotonic_ns", lambda: 60_000_000_000),
            **kwargs,
        )

    def test_phase_two_records_login_to_marker_monotonic_duration(self) -> None:
        artifact = self.collect()
        self.assertEqual(artifact["schema"], "wsm-desktop-session-readiness/1")
        self.assertEqual(artifact["marker"], "plasma-autostart-phase-2")
        self.assertEqual(artifact["phase"], 2)
        self.assertEqual(artifact["status"], "available")
        self.assertEqual(artifact["timing"]["login_to_phase2_ms"], 10_000.0)
        self.assertEqual(artifact["timing"]["session_start_monotonic_us"], 50_000_000)
        self.assertNotIn("id_digest", artifact["session"])
        self.assertEqual(artifact["session"]["type"], "x11")

    def test_fixed_loginctl_argv_and_no_shell(self) -> None:
        artifact = self.collect()
        command = self.runner.call_args.args[0]
        options = self.runner.call_args.kwargs
        self.assertEqual(
            command,
            [
                "/usr/bin/loginctl",
                "show-session",
                "8",
                "--property=Id",
                "--property=TimestampMonotonic",
            ],
        )
        self.assertNotIn("shell", options)
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        self.assertTrue(options["capture_output"])
        self.assertEqual(options["env"]["LC_ALL"], "C")
        self.assertEqual(options["timeout"], session.LOGINCTL_TIMEOUT_SECONDS)
        self.assertNotIn("USER", json.dumps(artifact))

    def test_missing_loginctl_keeps_marker_but_latency_unknown(self) -> None:
        artifact = self.collect(which=lambda name: None)
        self.assertEqual(artifact["status"], "partial")
        self.assertIsNone(artifact["timing"]["session_start_monotonic_us"])
        self.assertIsNone(artifact["timing"]["login_to_phase2_ms"])
        self.runner.assert_not_called()

    def test_session_self_fallback_does_not_require_xdg_session_id(self) -> None:
        self.environment.pop("XDG_SESSION_ID")
        artifact = self.collect()
        self.assertEqual(self.runner.call_args.args[0][2], "self")
        self.assertEqual(artifact["status"], "available")

    def test_invalid_session_id_is_not_passed_to_loginctl(self) -> None:
        self.environment["XDG_SESSION_ID"] = "../other-session"
        artifact = self.collect()
        self.assertEqual(artifact["status"], "partial")
        self.assertNotIn("id_digest", artifact["session"])
        self.runner.assert_not_called()

    def test_failed_or_malformed_loginctl_is_unknown_not_zero(self) -> None:
        self.runner.return_value = subprocess.CompletedProcess(
            ["loginctl"], 1, stdout="", stderr="private diagnostic",
        )
        artifact = self.collect()
        self.assertIsNone(artifact["timing"]["login_to_phase2_ms"])
        self.assertEqual(artifact["status"], "partial")
        self.assertNotIn("private diagnostic", json.dumps(artifact))

        self.runner.return_value = subprocess.CompletedProcess(
            ["loginctl"], 0, stdout="Id=8\nTimestampMonotonic=not-a-number\n", stderr="",
        )
        artifact = self.collect()
        self.assertIsNone(artifact["timing"]["login_to_phase2_ms"])

    def test_timeout_keeps_marker_and_unknown_latency(self) -> None:
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

        artifact = self.collect(runner=timeout)
        self.assertEqual(artifact["status"], "partial")
        self.assertIsNone(artifact["timing"]["login_to_phase2_ms"])

    def test_wrong_clock_order_does_not_create_negative_latency(self) -> None:
        artifact = self.collect(monotonic_ns=lambda: 40_000_000_000)
        self.assertEqual(artifact["status"], "partial")
        self.assertIsNone(artifact["timing"]["session_start_monotonic_us"])
        self.assertIsNone(artifact["timing"]["login_to_phase2_ms"])

    def test_only_kde_session_is_accepted(self) -> None:
        self.environment["XDG_CURRENT_DESKTOP"] = "GNOME"
        with self.assertRaises(session.SessionReadinessError):
            self.collect()
        self.runner.assert_not_called()

    def test_schema_accepts_realistic_available_and_partial_artifacts(self) -> None:
        with SCHEMA_PATH.open(encoding="utf-8") as stream:
            schema = json.load(stream)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())

        available = self.collect()
        self.assertEqual(list(validator.iter_errors(available)), [])

        partial = self.collect(which=lambda name: None)
        self.assertEqual(list(validator.iter_errors(partial)), [])

    def test_runtime_artifact_is_atomic_private_and_contains_no_raw_session_id(self) -> None:
        artifact = self.collect()
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary) / "runtime"
            runtime.mkdir(mode=0o700)
            runtime.chmod(0o700)
            target = session.write_session_readiness(
                artifact, runtime_dir=runtime, uid=os.geteuid(),
            )
            self.assertTrue(target.is_file())
            self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            data = target.read_text(encoding="utf-8")
            self.assertNotIn('"8"', data)
            self.assertNotIn("must-not-be-recorded", data)
            self.assertTrue(target.name.startswith("plasma-phase2-"))

    def test_runtime_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_runtime = root / "real"
            real_runtime.mkdir(mode=0o700)
            real_runtime.chmod(0o700)
            symlink = root / "runtime"
            symlink.symlink_to(real_runtime, target_is_directory=True)
            with self.assertRaises(session.SessionReadinessError):
                session.write_session_readiness(
                    self.collect(), runtime_dir=symlink, uid=os.geteuid(),
                )


if __name__ == "__main__":
    unittest.main()
