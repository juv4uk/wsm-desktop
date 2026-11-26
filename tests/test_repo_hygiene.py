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
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

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
            matches = find_pipe_to_shell(path.read_text(encoding="utf-8", errors="replace"))
            offenders.extend(f"{path.relative_to(ROOT)}: {item}" for item in matches)
        self.assertEqual(offenders, [], "pipe-to-shell found: " + "; ".join(offenders))

    def test_scripts_never_pipe_a_download_into_a_shell(self) -> None:
        offenders: list[str] = []
        for path in SCRIPTS.rglob("*"):
            if not path.is_file():
                continue
            matches = find_pipe_to_shell(path.read_text(encoding="utf-8", errors="replace"))
            offenders.extend(f"{path.relative_to(ROOT)}: {item}" for item in matches)
        self.assertEqual(offenders, [], "pipe-to-shell found: " + "; ".join(offenders))

    def test_multiline_download_pipe_is_detected(self) -> None:
        source = (
            "curl --fail --location https://example.invalid/install.sh \\\n"
            "  | sudo bash"
        )
        self.assertEqual(len(find_pipe_to_shell(source)), 1)

    def test_download_to_file_is_not_flagged(self) -> None:
        source = (
            "curl --fail --location --output install.sh https://example.invalid/install.sh\n"
            "sha256sum install.sh\n"
            "sed -n '1,80p' install.sh\n"
            "bash install.sh"
        )
        self.assertEqual(find_pipe_to_shell(source), [])


class NoShellInterpretationTests(unittest.TestCase):
    """Prevent command text from being parsed by a shell, including import aliases."""

    def test_project_python_does_not_call_shell_interpreting_apis(self) -> None:
        offenders: list[str] = []
        for directory in ("scripts", "wsm_install", "wsm_hwcheck"):
            for path in sorted((ROOT / directory).rglob("*.py")):
                found = find_unsafe_shell_calls(
                    path.read_text(encoding="utf-8", errors="replace")
                )
                offenders.extend(f"{path.relative_to(ROOT)}: {item}" for item in found)
        self.assertEqual(offenders, [], "shell interpretation found: " + "; ".join(offenders))

    def test_ast_guard_detects_module_and_direct_import_aliases(self) -> None:
        source = (
            "import subprocess as sp\n"
            "sp.run(['echo', 'x'], shell=True)\n"
            "from os import system as run_command\n"
            "run_command('id')\n"
            "from asyncio import create_subprocess_shell as spawn\n"
            "spawn('echo x')\n"
        )
        found = find_unsafe_shell_calls(source)
        self.assertEqual(len(found), 3)

    def test_ast_guard_ignores_comments_and_string_literals(self) -> None:
        source = (
            "# subprocess.run(command, shell=True) is forbidden\n"
            "example = \"os.system('not executed')\"\n"
            "subprocess.run(['echo', 'safe'], check=True)\n"
        )
        self.assertEqual(find_unsafe_shell_calls(source), [])


class ShellSyntaxTests(unittest.TestCase):
    def test_every_shell_script_parses(self) -> None:
        for path in sorted(SCRIPTS.rglob("*.sh")):
            with self.subTest(script=path.relative_to(ROOT)):
                completed = subprocess.run(
                    ["bash", "-n", str(path)], capture_output=True, text=True, check=False
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)


class InstallerFrontendTests(unittest.TestCase):
    """The CLI is the primary path: a GUI installer needs hardware we may not have."""

    def test_installer_document_names_the_cli_as_primary(self) -> None:
        text = (ROOT / "docs" / "INSTALLER.md").read_text(encoding="utf-8")
        self.assertIn("--guided", text)
        self.assertIn("--tui", text)
        self.assertIn("APPLY вимкнено", text)

    def test_calamares_module_is_marked_optional(self) -> None:
        text = (ROOT / "installer" / "calamares" / "README.md").read_text(encoding="utf-8")
        self.assertIn("опційний", text.lower())

    def test_both_frontends_call_the_same_backend(self) -> None:
        """Two frontends must not mean two implementations of mkfs."""
        module = (ROOT / "installer" / "calamares" / "modules" / "wsm_deploy" / "main.py").read_text(encoding="utf-8")
        self.assertIn("wsm_install.executor", module)
        self.assertIn("wsm_install.install_steps", module)
        self.assertIn("wsm_install.partition", module)
        self.assertIn("execute.apply-disabled", module)
        # No direct runner: the common executor owns all command policy.
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

    def test_runtime_artifact_producers_publish_their_schema_constant(self) -> None:
        from measure_baseline import SCHEMA as PERF_SCHEMA
        from verify_live_release import SCHEMA as RELEASE_SCHEMA
        from wsm_hwcheck.isa import SCHEMA as CPU_ISA_SCHEMA

        self.assertEqual(CPU_ISA_SCHEMA, "wsm-cpu-isa/1")
        self.assertEqual(PERF_SCHEMA, "wsm-perf-baseline/1")
        self.assertEqual(RELEASE_SCHEMA, "wsm-release-verdict/1")


if __name__ == "__main__":
    unittest.main()
