# SPDX-License-Identifier: LicenseRef-Volnist
"""A Guix signing key must round-trip, or the cache is unusable."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "guix_sign.py"

NARINFO = (
    "StorePath: /gnu/store/8bjy9g0cssjrw9ljz2r8ww1sma95isfj-wsm-tools-0.1.0-rc6\n"
    "NarHash: sha256:0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9\n"
    "NarSize: 8388608\n"
    "References: \n"
)


class KeyTests(unittest.TestCase):
    def keygen(self, directory: Path) -> tuple[Path, Path]:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "keygen"],
            cwd=directory, capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return directory / "signing-key.sec", directory / "signing-key.pub"

    def test_the_public_key_has_the_shape_guix_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, public = self.keygen(Path(tmp))
            text = public.read_text(encoding="utf-8")
        self.assertIn("(public-key", text)
        self.assertIn("(curve Ed25519)", text)
        self.assertRegex(text, r"\(q #[0-9A-F]{64}#\)")
        # The public key must not leak the scalar.
        self.assertNotIn("(d #", text)

    def test_the_private_key_carries_both_q_and_d(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            private, _ = self.keygen(Path(tmp))
            text = private.read_text(encoding="utf-8")
            mode = private.stat().st_mode & 0o777
        self.assertRegex(text, r"\(q #[0-9A-F]{64}#\)")
        self.assertRegex(text, r"\(d #[0-9A-F]{64}#\)")
        self.assertEqual(mode, 0o400, "a private key must not be world-readable")

    def test_keygen_refuses_to_overwrite(self) -> None:
        """Silently replacing a signing key would invalidate every client's trust."""
        with tempfile.TemporaryDirectory() as tmp:
            self.keygen(Path(tmp))
            again = subprocess.run(
                [sys.executable, str(SCRIPT), "keygen"],
                cwd=Path(tmp), capture_output=True, text=True, check=False,
            )
        self.assertNotEqual(again.returncode, 0)

    def test_a_signature_has_the_narinfo_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            private, _ = self.keygen(directory)
            body = directory / "n.txt"
            body.write_text(NARINFO, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "sign", str(body), str(private), "host"],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertRegex(completed.stdout.strip(), r"^1;host;[A-Za-z0-9+/=]+$")

    def test_two_runs_sign_the_same_bytes_identically(self) -> None:
        """RFC 6979 is deterministic; a random nonce would break reproduction."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            private, _ = self.keygen(directory)
            body = directory / "n.txt"
            body.write_text(NARINFO, encoding="utf-8")
            signatures = [
                subprocess.run(
                    [sys.executable, str(SCRIPT), "sign", str(body), str(private), "h"],
                    capture_output=True, text=True, check=True,
                ).stdout.strip()
                for _ in range(2)
            ]
        self.assertEqual(signatures[0], signatures[1])


class NoThirdPartyTests(unittest.TestCase):
    def test_the_script_uses_only_the_standard_library(self) -> None:
        """CI must run it on a runner with nothing installed."""
        text = SCRIPT.read_text(encoding="utf-8")
        imports = set(re.findall(r"^(?:import|from) (\w+)", text, re.M))
        allowed = {"argparse", "base64", "hashlib", "hmac", "os", "sys", "pathlib", "secrets", "typing", "__future__"}
        self.assertEqual(imports - allowed, set())


if __name__ == "__main__":
    unittest.main()
