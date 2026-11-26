# SPDX-License-Identifier: LicenseRef-Volnist
"""Rules learned from Omarchy, enforced instead of promised.

See docs/LESSONS-FROM-OMARCHY.md. The short version: a project whose glue layer
grows as untested shell scripts ends up with nobody able to say whether it
works, and installing by piping a download into a shell is not an installer.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

# curl ... | sh, wget ... | bash, and the eval-the-download variants.
PIPE_TO_SHELL = re.compile(
    r"\b(?:curl|wget)\b[^|\n]*\|\s*(?:sudo\s+)?(?:bash|sh)\b",
    re.IGNORECASE,
)


def find_pipe_to_shell(source: str) -> list[str]:
    """Find download-to-shell pipes, including backslash-newline continuation."""
    normalized = re.sub(r"\\\r?\n[ \t]*", " ", source)
    return [match.group(0) for match in PIPE_TO_SHELL.finditer(normalized)]


def _call_name(
    node: ast.AST,
    module_aliases: dict[str, str],
    direct_imports: dict[str, str],
) -> str | None:
    if isinstance(node, ast.Name):
        return direct_imports.get(node.id, module_aliases.get(node.id, node.id))
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value, module_aliases, direct_imports)
        return f"{parent}.{node.attr}" if parent else None
    return None


def find_unsafe_shell_calls(source: str) -> list[str]:
    """Find known Python APIs that interpret a string as shell code."""
    tree = ast.parse(source)
    module_aliases: dict[str, str] = {}
    direct_imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"os", "subprocess", "asyncio"}:
                    module_aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module in {
            "os", "subprocess", "asyncio"
        }:
            for alias in node.names:
                direct_imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"

    always_shell = {
        "os.system", "os.popen", "subprocess.getoutput",
        "subprocess.getstatusoutput", "asyncio.create_subprocess_shell",
    }
    shell_keyword_apis = {
        "subprocess.run", "subprocess.Popen", "subprocess.call",
        "subprocess.check_call", "subprocess.check_output",
    }
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func, module_aliases, direct_imports)
        if name in always_shell:
            offenders.append(f"line {node.lineno}: {name}")
        elif name in shell_keyword_apis and any(
            keyword.arg == "shell"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        ):
            offenders.append(f"line {node.lineno}: {name}(shell=True)")
    return offenders


def documentation_files() -> list[Path]:
    return [
        path for path in ROOT.rglob("*.md")
        if ".git" not in path.parts and "skills" not in path.parts
    ]


class NoPipeToShellTests(unittest.TestCase):
    def test_documentation_never_pipes_a_download_into_a_shell(self) -> None:
        offenders: list[str] = []
        for path in documentation_files():
            for match in PIPE_TO_SHELL.finditer(path.read_text(encoding="utf-8", errors="replace")):
                offenders.append(f"{path.relative_to(ROOT)}: {match.group(0).strip()}")
        self.assertEqual(offenders, [], "pipe-to-shell found: " + "; ".join(offenders))

    def test_scripts_never_pipe_a_download_into_a_shell(self) -> None:
        offenders: list[str] = []
        for path in SCRIPTS.iterdir():
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in PIPE_TO_SHELL.finditer(text):
                offenders.append(f"{path.name}: {match.group(0).strip()}")
        self.assertEqual(offenders, [], "pipe-to-shell found: " + "; ".join(offenders))


class NoShellInterpretationTests(unittest.TestCase):
    """Omarchy 4.0.0 turned titles and device names into shell strings twice.

    The durable fix there was to stop letting a shell parse anything. Our code
    must keep that property: argv lists only, never a command string.
    """

    FORBIDDEN = (
        re.compile(r"shell\s*=\s*True"),
        re.compile(r"\bos\.system\s*\("),
        re.compile(r"\bos\.popen\s*\("),
    )

    def test_our_python_never_hands_a_string_to_a_shell(self) -> None:
        offenders: list[str] = []
        for directory in ("scripts", "wsm_install", "wsm_hwcheck"):
            for path in (ROOT / directory).rglob("*.py"):
                text = path.read_text(encoding="utf-8", errors="replace")
                for pattern in self.FORBIDDEN:
                    if pattern.search(text):
                        offenders.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
        self.assertEqual(offenders, [], "shell interpretation found: " + "; ".join(offenders))


class ScriptCoverageTests(unittest.TestCase):
    def test_every_script_is_referenced_by_a_test(self) -> None:
        """A script nobody tests is a script nobody can vouch for."""
        corpus = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in TESTS.glob("*.py")
        )
        uncovered = sorted(
            path.name for path in SCRIPTS.iterdir()
            if path.is_file() and path.stem not in corpus
        )
        self.assertEqual(uncovered, [], f"no test mentions: {uncovered}")

    def test_every_shell_script_parses(self) -> None:
        for path in sorted(SCRIPTS.glob("*.sh")):
            with self.subTest(script=path.name):
                completed = subprocess.run(
                    ["bash", "-n", str(path)], capture_output=True, text=True, check=False
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)


class CiOnlyScriptTests(unittest.TestCase):
    """scripts/ci_qemu_guest_smoke.sh runs only inside CI, so it is checked here.

    It is the exact shape Omarchy was criticised for: glue that nobody can run
    locally. Naming it in a test at least guarantees it parses and that its
    safety flags are present.
    """

    def test_ci_qemu_guest_smoke_declares_strict_mode(self) -> None:
        text = (SCRIPTS / "ci_qemu_guest_smoke.sh").read_text(encoding="utf-8")
        self.assertIn("set -Eeuo pipefail", text)
        self.assertIn("MARKER=", text)


class InstallerFrontendTests(unittest.TestCase):
    """The CLI is the primary path: a GUI installer needs hardware we may not have."""

    def test_installer_document_names_the_cli_as_primary(self) -> None:
        text = (ROOT / "docs" / "INSTALLER.md").read_text(encoding="utf-8")
        self.assertIn("Два входи, один бекенд", text)
        self.assertIn("CLI первинний", text)

    def test_calamares_module_is_marked_optional(self) -> None:
        text = (ROOT / "installer" / "calamares" / "README.md").read_text(encoding="utf-8")
        self.assertIn("опційний", text.lower())

    def test_both_frontends_call_the_same_backend(self) -> None:
        """Two frontends must not mean two implementations of mkfs."""
        module = (ROOT / "installer" / "calamares" / "modules" / "wsm_deploy" / "main.py").read_text(encoding="utf-8")
        self.assertIn("wsm_install.executor", module)
        self.assertIn("wsm_install.install_steps", module)
        self.assertIn("wsm_install.partition", module)
        # No direct subprocess use: the backend owns every command.
        self.assertNotIn("subprocess", module)


class DecisionStatusTests(unittest.TestCase):
    """Two ADRs must not both claim to be the accepted answer."""

    def test_only_one_installer_adr_claims_to_be_accepted(self) -> None:
        accepted = []
        for path in sorted((ROOT / "docs" / "decisions").glob("*.md")):
            text = path.read_text(encoding="utf-8")
            if "instal" not in text.lower()[:400]:
                continue
            head = text[:600].lower()
            if "статус: прийнято" in head or "status: accepted" in head:
                accepted.append(path.name)
        self.assertLessEqual(
            len(accepted), 1,
            f"more than one installer decision claims acceptance: {accepted}",
        )

    def test_adr_0008_cites_the_nixos_precedent(self) -> None:
        """The whole argument is that NixOS ships Calamares with the same architecture."""
        text = (ROOT / "docs" / "decisions" / "0008-calamares-backend-module.md").read_text(encoding="utf-8")
        self.assertIn("NixOS", text)
        self.assertIn("installation-cd-graphical-calamares.nix", text)
        self.assertIn("proposed", text.lower())

    def test_installer_document_states_that_nothing_is_chosen(self) -> None:
        text = (ROOT / "docs" / "INSTALLER.md").read_text(encoding="utf-8")
        self.assertIn("інсталятор не вибрано", text.lower())


class VersionedArtifactTests(unittest.TestCase):
    """A reader can only refuse an unknown version if the version is pinned."""

    def test_every_schema_pins_its_own_version(self) -> None:
        schemas = sorted((ROOT / "schemas").glob("*.json"))
        self.assertTrue(schemas, "no schemas found")
        for path in schemas:
            with self.subTest(schema=path.name):
                document = json.loads(path.read_text(encoding="utf-8"))
                properties = document.get("properties", {})
                pinned = any(
                    "const" in properties.get(field, {})
                    for field in ("schema", "schema_version")
                )
                self.assertTrue(
                    pinned,
                    f"{path.name} does not pin schema or schema_version with a const",
                )

    def test_runtime_artifacts_share_the_same_version_convention(self) -> None:
        """The Python producers must use the same <name>/<major> shape as the schemas."""
        producers = {
            "wsm_hwcheck/isa.py": "wsm-cpu-isa/1",
            "scripts/measure_baseline.py": "wsm-perf-baseline/1",
            "scripts/verify_live_release.py": "wsm-release-verdict/1",
        }
        for relative, expected in producers.items():
            with self.subTest(producer=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
