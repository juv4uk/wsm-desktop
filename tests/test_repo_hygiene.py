# SPDX-License-Identifier: LicenseRef-Volnist
"""Repository hygiene rules learned from Omarchy, tested at behavior boundaries.

See docs/LESSONS-FROM-OMARCHY.md. Static checks protect narrow safety policies;
shell behavior is covered by focused tests or the CI workflow that executes it.
A filename appearing in a test is not evidence that the script works.
"""

from __future__ import annotations

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

# curl ... | sh, wget ... | bash, including a shell line continuation.
PIPE_TO_SHELL = re.compile(
    r"(?:curl|wget)\b[^|;\n]*\|\s*(?:sudo\s+)?(?:ba)?sh\b",
    re.IGNORECASE,
)


def find_pipe_to_shell(source: str) -> list[str]:
    """Return unsafe download-to-shell command fragments.

    A backslash-newline is a shell continuation, so normalize it before
    matching. An ordinary newline is not joined: it starts a new command.
    """
    normalized = re.sub(r"\\\r?\n[ \t]*", " ", source)
    return [match.group(0) for match in PIPE_TO_SHELL.finditer(normalized)]


def documentation_files() -> list[Path]:
    return [
        path for path in ROOT.rglob("*.md")
        if ".git" not in path.parts and "skills" not in path.parts
    ]


class PipeToShellPolicyTests(unittest.TestCase):
    def test_documentation_never_pipes_a_download_into_a_shell(self) -> None:
        offenders: list[str] = []
        for path in documentation_files():
            matches = find_pipe_to_shell(
                path.read_text(encoding="utf-8", errors="replace")
            )
            offenders.extend(
                f"{path.relative_to(ROOT)}: {match}" for match in matches
            )
        self.assertEqual(offenders, [], "pipe-to-shell found: " + "; ".join(offenders))

    def test_scripts_never_pipe_a_download_into_a_shell(self) -> None:
        offenders: list[str] = []
        for path in SCRIPTS.rglob("*"):
            if not path.is_file():
                continue
            matches = find_pipe_to_shell(
                path.read_text(encoding="utf-8", errors="replace")
            )
            offenders.extend(f"{path.relative_to(ROOT)}: {match}" for match in matches)
        self.assertEqual(offenders, [], "pipe-to-shell found: " + "; ".join(offenders))

    def test_multiline_download_pipe_to_shell_is_detected(self) -> None:
        source = (
            "curl --fail --location https://example.invalid/install.sh \\\n"
            "  | sudo bash"
        )
        self.assertEqual(len(find_pipe_to_shell(source)), 1)

    def test_download_to_file_can_be_inspected_before_execution(self) -> None:
        source = (
            "curl --fail --location --output install.sh https://example.invalid/install.sh\n"
            "sha256sum install.sh\n"
            "sed -n '1,120p' install.sh\n"
            "bash install.sh"
        )
        self.assertEqual(find_pipe_to_shell(source), [])


class ShellSyntaxTests(unittest.TestCase):
    def test_every_shell_script_parses(self) -> None:
        """Syntax validation is real; it is not a claim of runtime correctness."""
        for path in sorted(SCRIPTS.rglob("*.sh")):
            with self.subTest(script=path.relative_to(ROOT)):
                completed = subprocess.run(
                    ["bash", "-n", str(path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)


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

    def test_runtime_producers_publish_the_schema_version_they_own(self) -> None:
        from measure_baseline import SCHEMA as PERF_SCHEMA
        from verify_live_release import SCHEMA as RELEASE_SCHEMA
        from wsm_hwcheck.isa import SCHEMA as CPU_ISA_SCHEMA

        self.assertEqual(CPU_ISA_SCHEMA, "wsm-cpu-isa/1")
        self.assertEqual(PERF_SCHEMA, "wsm-perf-baseline/1")
        self.assertEqual(RELEASE_SCHEMA, "wsm-release-verdict/1")


if __name__ == "__main__":
    unittest.main()
