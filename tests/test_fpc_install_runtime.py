# SPDX-License-Identifier: LicenseRef-Volnist
"""Runtime smoke test for the native FPC installer argument boundary."""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = (
    ROOT / "build" / "fpc" / "wsm_install",
    ROOT / "build" / "pascal" / "wsm-install",
)
BINARY = (
    Path(os.environ["WSM_FPC_INSTALL_BINARY"])
    if os.environ.get("WSM_FPC_INSTALL_BINARY")
    else next((p for p in CANDIDATES if p.is_file()), CANDIDATES[0])
)


@unittest.skipUnless(BINARY.is_file(), "the FPC workflow compiles wsm_install")
class InstallerRuntimeTests(unittest.TestCase):
    def test_invalid_option_fails_before_running_any_reader(self) -> None:
        result = subprocess.run(
            [str(BINARY), "--not-a-valid-option"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage: wsm-install", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
