# SPDX-License-Identifier: LicenseRef-Volnist
"""Guix live closure and fail-closed trusted executable resolution tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wsm_install.install_steps import (
    TRUSTED_TOOLS,
    TrustedToolResolutionError,
    resolve_trusted_tool,
)

ROOT = Path(__file__).resolve().parents[1]


class GuixLiveToolClosureTests(unittest.TestCase):
    def test_live_profiles_explicitly_include_partition_tool_packages(self) -> None:
        required = ("gptfdisk", "parted", "dosfstools")
        for relative in ("systems/live-minimal.scm", "systems/live.scm"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("(gnu packages disk)", source, relative)
            for package in required:
                self.assertIn(package, source, f"{relative} omits {package}")

    def test_guix_evaluation_builds_the_pinned_tool_packages(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("check-guix-live-tool-packages:", makefile)
        target = makefile.split("check-guix-live-tool-packages:", 1)[1].split("\n\n", 1)[0]
        self.assertIn("guix time-machine -C channels.lock.scm -- build gptfdisk parted dosfstools", target)
        self.assertIn("$(MAKE) check-guix-live-tool-packages", makefile.split("check-guix-eval:", 1)[1].split("\n\n", 1)[0])

    def test_trusted_tools_are_binary_names_not_fhs_paths(self) -> None:
        expected = {"sgdisk", "partprobe", "udevadm", "mkfs.ext4", "mkfs.fat", "mount", "mkdir"}
        self.assertTrue(expected.issubset(set(TRUSTED_TOOLS)))
        self.assertTrue(all("/" not in value for value in TRUSTED_TOOLS.values()))
        implementation = (ROOT / "wsm_install" / "install_steps.py").read_text(encoding="utf-8")
        self.assertNotIn("/usr/bin/", implementation)
        self.assertNotIn("/usr/sbin/", implementation)
        self.assertIn('Path("/run/current-system/profile")', implementation)
        self.assertIn('for directory in ("bin", "sbin")', implementation)

    def test_resolver_uses_only_system_profile_bin_and_sbin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary)
            for index, (name, binary) in enumerate(TRUSTED_TOOLS.items()):
                directory = "bin" if index % 2 == 0 else "sbin"
                target = profile / directory / binary
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                target.chmod(0o755)
                self.assertEqual(str(target), resolve_trusted_tool(name, profile_root=profile))

    def test_profile_symlink_to_store_executable_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store_binary = root / "store" / "sgdisk"
            profile_binary = root / "profile" / "bin" / "sgdisk"
            store_binary.parent.mkdir(parents=True)
            profile_binary.parent.mkdir(parents=True)
            store_binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            store_binary.chmod(0o555)
            profile_binary.symlink_to(store_binary)
            self.assertEqual(str(profile_binary), resolve_trusted_tool("sgdisk", profile_root=root / "profile"))

    def test_missing_or_non_executable_tool_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary)
            tool = next(iter(TRUSTED_TOOLS))
            target = profile / "bin" / TRUSTED_TOOLS[tool]
            target.parent.mkdir(parents=True)
            target.write_text("not executable", encoding="utf-8")
            target.chmod(0o644)
            with self.assertRaises(TrustedToolResolutionError):
                resolve_trusted_tool(tool, profile_root=profile)

    def test_duplicate_bin_and_sbin_tool_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary)
            tool = next(iter(TRUSTED_TOOLS))
            for directory in ("bin", "sbin"):
                target = profile / directory / TRUSTED_TOOLS[tool]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                target.chmod(0o755)
            with self.assertRaises(TrustedToolResolutionError):
                resolve_trusted_tool(tool, profile_root=profile)

    def test_unknown_tool_name_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(TrustedToolResolutionError):
                resolve_trusted_tool("arbitrary-host-command", profile_root=temporary)


if __name__ == "__main__":
    unittest.main()
