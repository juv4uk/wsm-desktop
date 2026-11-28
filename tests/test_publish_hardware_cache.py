# SPDX-License-Identifier: LicenseRef-Volnist
"""Publishing must refuse until the owner has named their decisions.

The script runs on the owner's machine, not here, so these tests check the part
that would otherwise fail silently: that it refuses without a licence decision,
refuses `--tune=native`, and never offers to publish the Compatibility profile.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "publish-hardware-cache.sh"


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )


class PublishHardwareCacheTests(unittest.TestCase):
    def test_the_script_is_syntactically_valid(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_it_refuses_without_a_licence_decision(self) -> None:
        completed = run("--cpu", "skylake", "--dry-run")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("#367", completed.stderr)

    def test_it_refuses_native_tuning(self) -> None:
        completed = run(
            "--cpu", "native",
            "--license-decision", "custom-record",
            "--channel-unsigned-accepted",
            "--dry-run",
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("native", completed.stderr)

    def test_it_refuses_an_unsigned_channel_without_explicit_acceptance(self) -> None:
        completed = run("--cpu", "skylake", "--license-decision", "custom-record", "--dry-run")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("guix-authorizations", completed.stderr)

    def test_a_complete_dry_run_prints_the_plan(self) -> None:
        completed = run(
            "--cpu", "skylake",
            "--license-decision", "custom-record",
            "--channel-unsigned-accepted",
            "--dry-run",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("guix publish", completed.stdout)
        self.assertIn("--tune=skylake", completed.stdout)

    def test_it_never_publishes_the_compatibility_profile(self) -> None:
        completed = run(
            "--cpu", "skylake",
            "--license-decision", "custom-record",
            "--channel-unsigned-accepted",
            "--dry-run",
        )
        self.assertNotIn("compatibility.scm", completed.stdout)
        self.assertNotIn("nvidia", completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()
