# SPDX-License-Identifier: LicenseRef-Volnist
"""Keep process-launch APIs out of the installer implementation.

This is a static AST denylist for known process-launch primitives. It is not a
proof against arbitrary dynamic code, native extensions, or runtime behaviour;
the QEMU/read-only and APPLY-disabled tests remain separate controls.
"""

from __future__ import annotations

import ast
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
    # os process primitives
    "os.system",
    "os.popen",
    "os.startfile",
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
    # indirect process helpers
    "pty.spawn",
    "pty.fork",
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
    "multiprocessing.Process",
    "multiprocessing.Pool",
    "multiprocessing.get_context",
    "concurrent.futures.ProcessPoolExecutor",
    "webbrowser.open",
    "webbrowser.open_new",
    "webbrowser.open_new_tab",
}

FORBIDDEN_MODULES = {"subprocess", "pty", "multiprocessing", "ctypes"}
DYNAMIC_IMPORT_APIS = {"__import__", "importlib.import_module"}
DYNAMIC_CODE_APIS = {"exec", "eval"}


def _qualified(node: ast.AST, aliases: dict[str, str]) -> str | None:
    """Resolve dotted names and the simple aliases used in installer code."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _qualified(node.value, aliases)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _targets(node: ast.AST) -> list[str]:
    """Return simple variable names assigned by an assignment target."""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [name for child in node.elts for name in _targets(child)]
    return []


def scan(source: str) -> list[str]:
    """Return source locations for known process launch/import primitives."""
    tree = ast.parse(source)
    aliases: dict[str, str] = {}
    findings: list[str] = []

    # First resolve imported module and function aliases.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                root = item.name.split(".")[0]
                bound = item.asname or root
                aliases[bound] = item.name if item.asname else root
                if root in FORBIDDEN_MODULES:
                    findings.append(f"line {node.lineno}: imports {root}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
            root = module.split(".")[0]
            if root in FORBIDDEN_MODULES:
                findings.append(f"line {node.lineno}: imports from {module}")
            for item in node.names:
                if item.name == "*":
                    # Wildcard imports make process-launch aliases unreviewable.
                    if root in {"os", "subprocess", "pty"}:
                        findings.append(f"line {node.lineno}: wildcard import from {module}")
                    continue
                aliases[item.asname or item.name] = f"{module}.{item.name}"

    # Then resolve direct assignments such as launch = os.system and chains
    # such as runner = launch, independent of AST walk order.
    for _ in range(len(aliases) + 2):
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if value is None:
                continue
            target_nodes = node.targets if isinstance(node, ast.Assign) else [node.target]
            resolved = _qualified(value, aliases)
            if not resolved:
                continue
            for target in target_nodes:
                for name in _targets(target):
                    if aliases.get(name) != resolved:
                        aliases[name] = resolved
                        changed = True
        if not changed:
            break

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        name = _qualified(node.func, aliases)
        if name in SPAWN_APIS:
            findings.append(f"line {node.lineno}: calls {name}")
            continue
        if name in DYNAMIC_CODE_APIS:
            findings.append(f"line {node.lineno}: calls dynamic code API {name}")
            continue

        # getattr(os, "system"), __import__("subprocess"), and
        # importlib.import_module("subprocess") hide the target from dotted
        # attribute matching, so inspect their literal arguments.
        if isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) >= 2:
            module = _qualified(node.args[0], aliases)
            member = node.args[1]
            if isinstance(member, ast.Constant) and isinstance(member.value, str):
                target = f"{module}.{member.value}" if module else member.value
                if target in SPAWN_APIS:
                    findings.append(f"line {node.lineno}: getattr resolves {target}")
                    continue

        if name in DYNAMIC_IMPORT_APIS and node.args:
            module_arg = node.args[0]
            if isinstance(module_arg, ast.Constant) and isinstance(module_arg.value, str):
                root = module_arg.value.split(".")[0]
                if root in FORBIDDEN_MODULES:
                    findings.append(f"line {node.lineno}: dynamically imports {root}")

    return sorted(set(findings))


class InstallerNoSpawnTest(unittest.TestCase):
    def test_guarded_directories_exist(self) -> None:
        for directory in GUARDED_DIRS:
            self.assertTrue((ROOT / directory).is_dir(), directory)

    def test_no_known_spawn_primitive_in_the_installer(self) -> None:
        offenders: list[str] = []
        for directory in GUARDED_DIRS:
            for path in sorted((ROOT / directory).rglob("*.py")):
                findings = scan(path.read_text(encoding="utf-8"))
                offenders.extend(
                    f"{path.relative_to(ROOT)}: {finding}" for finding in findings
                )
        self.assertEqual(
            offenders,
            [],
            "installer modules must not import or call process-launch APIs",
        )

    def test_detector_catches_module_and_function_aliases(self) -> None:
        bad = (
            "import subprocess as sp\n"
            "launch = sp.run\n"
            "runner = launch\n"
            "runner(['/bin/true'])\n"
        )
        self.assertTrue(scan(bad))

    def test_detector_catches_dotted_and_from_imports(self) -> None:
        bad = (
            "import subprocess.helpers\n"
            "from os import system as launch\n"
            "launch('true')\n"
        )
        self.assertTrue(scan(bad))

    def test_detector_catches_dynamic_access_and_imports(self) -> None:
        bad = (
            "import os\n"
            "getattr(os, 'system')('true')\n"
            "__import__('subprocess')\n"
        )
        self.assertTrue(scan(bad))

    def test_detector_rejects_dynamic_code_execution(self) -> None:
        self.assertTrue(scan("exec('import os; os.system(\"true\")')\n"))

    def test_detector_allows_harmless_code(self) -> None:
        fine = (
            "from pathlib import Path\n"
            "def read(path):\n"
            "    return Path(path).read_text()\n"
        )
        self.assertEqual(scan(fine), [])


if __name__ == "__main__":
    unittest.main()
