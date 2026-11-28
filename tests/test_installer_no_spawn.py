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


# --- second axis: writing to a device without spawning anything -------------
#
# The spawn guard above stops the installer from running mkfs. It does not stop
# it from opening /dev/vda for writing and doing the work itself, which needs no
# process at all. These checks close the obvious half of that gap.

OPEN_CALLS = {"open", "io.open", "Path.open", "os.open", "io.FileIO", "os.fdopen"}


def _is_device_path(node: ast.expr) -> bool:
    """A literal that names a device or a sysfs entry."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value
        return text.startswith("/dev/") or text.startswith("/sys/") or text == "/dev"
    return False


def _write_intent(node: ast.Call, name: str) -> bool:
    """True when the call can write.

    For open()/Path.open()/io.open() the default mode is "r", so a missing mode is
    a read. For os.open()/io.FileIO() the mode is a flags integer, and when it is
    not visible we assume the unsafe case rather than guessing.
    """
    saw_mode = False
    for argument in node.args[1:3]:
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            saw_mode = True
            if any(flag in argument.value for flag in ("w", "a", "x", "+")):
                return True
        elif isinstance(argument, ast.Attribute) and argument.attr == "O_RDONLY":
            saw_mode = True
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            value = keyword.value.value
            if isinstance(value, str):
                saw_mode = True
                if any(flag in value for flag in ("w", "a", "x", "+")):
                    return True
    if saw_mode:
        return False
    return name in {"os.open", "io.FileIO"}


def _call_name(node: ast.Call, aliases: dict[str, str]) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return aliases.get(func.id, func.id)
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        module = aliases.get(func.value.id, func.value.id)
        return f"{module}.{func.attr}"
    return None


def scan_device_writes(source: str) -> list[str]:
    """Return one finding per way to reach a device for writing.

    Raw descriptors are not forbidden by themselves: guix_deploy._write_new_file
    uses os.open with O_EXCL|O_NOFOLLOW to create a private file safely, and a
    blanket ban would push people away from that pattern. What is forbidden is
    naming a device or a sysfs path with write intent.
    """
    tree = ast.parse(source)
    aliases: dict[str, str] = {}
    findings: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = _call_name(node, aliases)
        if name not in OPEN_CALLS:
            continue
        if not _is_device_path(node.args[0]):
            continue
        if _write_intent(node, name):
            findings.append(f"line {node.lineno}: opens a device for writing ({name})")
    return findings


class InstallerNoDeviceWriteTest(unittest.TestCase):
    """A static scan, and it says what it cannot see.

    It catches a device named as a literal with write intent. It does not catch
    open(dev, "r+b") where dev is a variable, because nothing static can. That
    limit is the reason a runtime audit hook remains the right long-term fix; this
    test closes the case that gets written by accident.
    """

    def test_no_device_is_opened_for_writing(self) -> None:
        offenders: list[str] = []
        for directory in GUARDED_DIRS:
            for path in sorted((ROOT / directory).rglob("*.py")):
                findings = scan_device_writes(path.read_text(encoding="utf-8"))
                offenders.extend(
                    f"{path.relative_to(ROOT)}: {finding}" for finding in findings
                )
        self.assertEqual(offenders, [], "installer must not write to a device directly")

    def test_the_device_scan_catches_a_literal_device_open(self) -> None:
        bad = 'def zap():\n    open("/dev/vda", "r+b")\n'
        self.assertTrue(scan_device_writes(bad))

    def test_the_device_scan_catches_a_raw_descriptor(self) -> None:
        self.assertTrue(scan_device_writes("import os\nos.open('/dev/vda', os.O_RDWR)\n"))

    def test_the_device_scan_allows_reading_a_sysfs_value(self) -> None:
        fine = 'value = open("/sys/class/drm/card0/device/vendor").read()\n'
        self.assertEqual(scan_device_writes(fine), [])


if __name__ == "__main__":
    unittest.main()
