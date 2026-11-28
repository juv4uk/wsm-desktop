# SPDX-License-Identifier: LicenseRef-Volnist
"""Runtime tests for the native, read-only FPC installer preflight."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = (
    ROOT / "build" / "fpc" / "wsm_preflight",
    ROOT / "build" / "pascal" / "wsm-preflight",
)
BINARY = (
    Path(os.environ["WSM_FPC_PREFLIGHT_BINARY"])
    if os.environ.get("WSM_FPC_PREFLIGHT_BINARY")
    else next((p for p in CANDIDATES if p.is_file()), CANDIDATES[0])
)


@unittest.skipUnless(BINARY.is_file(), "the FPC workflow compiles wsm_preflight")
class PreflightRuntimeTests(unittest.TestCase):
    def test_preflight_emits_json_and_keeps_missing_report_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system_file = root / "desktop.scm"
            system_file.write_text("(operating-system)\n", encoding="utf-8")
            result = subprocess.run(
                [
                    str(BINARY),
                    "--mount-point", directory,
                    "--system-file", str(system_file),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertIn(result.returncode, (1, 6), result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["schema"], "wsm-preflight/1")
        report = next(item for item in output["criteria"] if item["id"] == "report")
        self.assertEqual(report["status"], "not-run")
        self.assertIn("incomplete is not a pass", output["note"])


if __name__ == "__main__":
    unittest.main()
