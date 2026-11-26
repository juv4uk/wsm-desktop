# SPDX-License-Identifier: LicenseRef-Volnist
"""A fixed `/tmp` path is allowed only inside the disposable guest.

Omarchy's November 2026 hardening batch (#19965, #19998) is mostly about
predictable paths in world-writable directories: fixed `/tmp` filenames,
`mktemp`+`rm` races, and lock files that anyone can replace.

WSM does use fixed `/tmp` names — but only inside `GUEST_INIT`, the shell script
that runs in a single-user disposable QEMU guest. That is acceptable there and
nowhere else. The danger is not today's code; it is the next agent copying the
pattern into host-side code, where `/tmp` really is shared.

So the rule this test enforces is narrow and checkable: a literal `/tmp/...`
path may exist in exactly one module, and only inside the guest script constant.
Host-side code uses `tempfile`, which produces an unpredictable name.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUEST_SCRIPT = ROOT / "scripts" / "ci_qemu_hwcheck_guest.py"
GUEST_CONSTANT = "GUEST_INIT"
SEARCH_ROOTS = ("wsm_install", "wsm_hwcheck", "wsm_perf", "scripts", "wsm")


def python_files() -> list[Path]:
    found: list[Path] = []
    for name in SEARCH_ROOTS:
        directory = ROOT / name
        if directory.is_dir():
            found.extend(sorted(directory.rglob("*.py")))
    return found


def fixed_temp_literals(source: Path) -> list[tuple[int, str]]:
    """Line numbers of string literals that name a fixed path under /tmp."""
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith("/tmp/"):
                found.append((node.lineno, node.value))
    return found


def guest_constant_lines(source: Path) -> tuple[int, int]:
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == GUEST_CONSTANT:
                    return node.lineno, node.end_lineno or node.lineno
    raise AssertionError(f"{source} has no {GUEST_CONSTANT} assignment")


class FixedTempPathTests(unittest.TestCase):
    def test_fixed_tmp_paths_exist_only_inside_the_guest_script(self) -> None:
        violations: list[str] = []
        for source in python_files():
            literals = fixed_temp_literals(source)
            if not literals:
                continue
            if source != GUEST_SCRIPT:
                violations.extend(
                    f"{source.relative_to(ROOT)}:{line}: {value!r}" for line, value in literals
                )
                continue
            start, end = guest_constant_lines(source)
            violations.extend(
                f"{source.relative_to(ROOT)}:{line}: {value!r} is outside {GUEST_CONSTANT}"
                for line, value in literals
                if not start <= line <= end
            )
        self.assertEqual(violations, [], "fixed /tmp paths leaked into host-side code")

    def test_host_side_writers_use_tempfile(self) -> None:
        """A file the host creates itself must get an unpredictable name."""
        cli = (ROOT / "wsm_install" / "cli.py").read_text(encoding="utf-8")
        self.assertIn("tempfile.mkstemp", cli)
        self.assertNotIn('"/tmp/', cli)


if __name__ == "__main__":
    unittest.main()
