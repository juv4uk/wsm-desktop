# SPDX-License-Identifier: LicenseRef-Volnist
"""The installer must contain no way to start a process, not just no shell.

`test_repo_hygiene` forbids shell-style calls (`os.system`, `subprocess.run(...,
shell=True)` and friends). That is a different property: it protects against
command-text injection, and it lets `subprocess.run(["/bin/true"])` through,
because no shell is involved.

The installer's documented guarantee is stronger — APPLY is disabled and nothing
is ever executed on the target disk. A hidden `subprocess.run` inside the
per-step loop would run real commands while the report still said `not-run`,
which is exactly what this test exists to prevent.

It is a denylist, and a denylist is weaker than an audit hook that observes
spawns at runtime. But it closes the gap that matters today: every ordinary
spelling of "start a process" in the two directories that must never do it.
"""

from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARDED_DIRS = ("wsm_install", "installer")

SPAWN_APIS = {
    # subprocess
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.getoutput",
    "subprocess.getstatusoutput",
    "subprocess.run_async",
    # os process primitives
    "os.system",
    "os.popen",
    "os.execv",
    "os.execve",
    "os.execvp",
    "os.execvpe",
    "os.execl",
    "os.execle",
    "os.execlp",
    "os.execlpe",
    "os.posix_spawn",
    "os.posix_spawnp",
    "os.spawnl",
    "os.spawnle",
    "os.spawnlp",
    "os.spawnlpe",
    "os.spawnv",
    "os.spawnve",
    "os.spawnvp",
    "os.spawnvpe",
    "os.fork",
    "os.forkpty",
    # other ways to reach a process
    "pty.spawn",
    "pty.fork",
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
    "multiprocessing.Process",
    "multiprocessing.Pool",
}

FORBIDDEN_MODULES = {"subprocess", "pty", "multiprocessing", "ctypes"}


def _resolve(node: ast.Call, aliases: dict[str, str]) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        module = aliases.get(func.value.id, func.value.id)
        return f"{module}.{func.attr}"
    return None


def _dynamic_spawn(node: ast.Call) -> bool:
    """getattr(subprocess, "run") and similar indirection."""
    if not isinstance(node.func, ast.Name) or node.func.id != "getattr":
        return False
    return any(
        isinstance(argument, ast.Constant)
        and isinstance(argument.value, str)
        and argument.value
        in {
            "run", "Popen", "call", "check_call", "check_output",
            "system", "popen", "execv", "execve", "fork", "posix_spawn",
            "spawn", "create_subprocess_exec",
        }
        for argument in node.args[1:2]
    )


def scan(source: str) -> list[str]:
    """Return one finding per spawn primitive found in `source`."""
    tree = ast.parse(source)
    aliases: dict[str, str] = {}
    findings: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                aliases[alias.asname or root] = alias.name
                if alias.name in FORBIDDEN_MODULES:
                    findings.append(f"line {node.lineno}: imports {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FORBIDDEN_MODULES:
                findings.append(f"line {node.lineno}: from {node.module} import ...")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _dynamic_spawn(node):
            findings.append(f"line {node.lineno}: getattr(...) resolving a spawn API")
            continue
        name = _resolve(node, aliases)
        if name in SPAWN_APIS:
            findings.append(f"line {node.lineno}: calls {name}")

    return findings


class InstallerNoSpawnTest(unittest.TestCase):
    def test_guarded_directories_exist(self) -> None:
        for directory in GUARDED_DIRS:
            self.assertTrue((ROOT / directory).is_dir(), directory)

    def test_no_spawn_primitive_in_the_installer(self) -> None:
        offenders: list[str] = []
        for directory in GUARDED_DIRS:
            for path in sorted((ROOT / directory).rglob("*.py")):
                findings = scan(path.read_text(encoding="utf-8"))
                offenders.extend(
                    f"{path.relative_to(ROOT)}: {finding}" for finding in findings
                )
        self.assertEqual(offenders, [], "installer must not be able to start a process")

    def test_the_detector_itself_catches_a_hidden_spawn(self) -> None:
        """Negative control: without this, a broken detector looks like a clean tree."""
        bad = (
            "import subprocess\n"
            "def step():\n"
            "    subprocess.run(['/bin/true'])\n"
        )
        self.assertTrue(scan(bad))

    def test_the_detector_catches_indirection(self) -> None:
        bad = (
            "import subprocess\n"
            "runner = getattr(subprocess, 'run')\n"
            "runner(['/bin/true'])\n"
        )
        self.assertTrue(scan(bad))

    def test_the_detector_catches_a_plain_import(self) -> None:
        self.assertTrue(scan("import ctypes\n"))

    def test_the_detector_allows_harmless_code(self) -> None:
        fine = "from pathlib import Path\n\ndef read(p):\n    return Path(p).read_text()\n"
        self.assertEqual(scan(fine), [])


if __name__ == "__main__":
    unittest.main()
