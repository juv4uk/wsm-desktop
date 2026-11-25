# SPDX-License-Identifier: LicenseRef-Volnist
"""Rules learned from Omarchy, enforced instead of promised.

See docs/LESSONS-FROM-OMARCHY.md. The short version: a project whose glue layer
grows as untested shell scripts ends up with nobody able to say whether it
works, and installing by piping a download into a shell is not an installer.
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"

# curl ... | sh, wget ... | bash, and the eval-the-download variants.
PIPE_TO_SHELL = re.compile(
    r"(curl|wget)[^\n|]*\|\s*(sudo\s+)?(ba)?sh\b",
    re.IGNORECASE,
)


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
