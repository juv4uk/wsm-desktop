# SPDX-License-Identifier: LicenseRef-Volnist
"""Behaviour of the document-ownership gate, not the state of the repository.

Each fixture is a miniature repository. The test asserts that the checker
turns red for the exact defect it exists for and green once the defect is
fixed, so the gate cannot rot into a file that merely mentions a rule.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_doc_ownership.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_doc_ownership", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = load_checker()


class Fixture:
    """A throwaway repository with the entry points already in place."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for name in ("AGENTS.md", "CONTRIBUTING.md", "SECURITY.md"):
            self.write(name, f"# {name}\n")
        self.write("docs/DECISIONS.md", "# Реєстр\n")
        self.write("README.md", "# README\n\n[реєстр рішень](docs/DECISIONS.md)\n")

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def cleanup(self) -> None:
        self._tmp.cleanup()


class DocumentOwnershipTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()
        self.addCleanup(self.fixture.cleanup)

    def errors(self) -> list[str]:
        return checker.check(self.fixture.root)

    def test_clean_repository_passes(self) -> None:
        self.fixture.write("README.md", "# README\n\n[реєстр](docs/DECISIONS.md), [огляд](docs/OVERVIEW.md)\n")
        self.fixture.write("docs/OVERVIEW.md", "# Огляд\n")
        self.assertEqual(self.errors(), [])

    def test_unregistered_adr_fails(self) -> None:
        self.fixture.write("docs/decisions/0001-example.md", "# ADR\n")
        errors = self.errors()
        self.assertTrue(
            any("0001-example.md" in error and "not registered" in error for error in errors),
            errors,
        )

    def test_registered_adr_passes(self) -> None:
        self.fixture.write("docs/decisions/0001-example.md", "# ADR\n")
        self.fixture.write(
            "docs/DECISIONS.md",
            "# Реєстр\n\n| Тема | Документ |\n| --- | --- |\n"
            "| Приклад | [ADR 0001](decisions/0001-example.md) |\n",
        )
        self.assertEqual(self.errors(), [])

    def test_orphan_document_fails(self) -> None:
        self.fixture.write("docs/ORPHAN.md", "# Нікому не потрібен\n")
        errors = self.errors()
        self.assertTrue(any("docs/ORPHAN.md" in error for error in errors), errors)

    def test_document_reachable_through_a_chain_passes(self) -> None:
        self.fixture.write("README.md", "# README\n\n[реєстр](docs/DECISIONS.md), [огляд](docs/OVERVIEW.md)\n")
        self.fixture.write("docs/OVERVIEW.md", "# Огляд\n\n[деталі](DETAILS.md)\n")
        self.fixture.write("docs/DETAILS.md", "# Деталі\n")
        self.assertEqual(self.errors(), [])

    def test_two_orphans_linking_each_other_still_fail(self) -> None:
        """The rule is reachability from an entry point, not "someone links to me"."""
        self.fixture.write("docs/ONE.md", "[два](TWO.md)\n")
        self.fixture.write("docs/TWO.md", "[один](ONE.md)\n")
        errors = self.errors()
        self.assertTrue(any("docs/ONE.md" in error for error in errors), errors)
        self.assertTrue(any("docs/TWO.md" in error for error in errors), errors)

    def test_unlinked_translation_fails(self) -> None:
        self.fixture.write("docs/GUIDE.md", "# Настанова\n")
        self.fixture.write("docs/GUIDE.en.md", "# Guide\n")
        errors = self.errors()
        self.assertTrue(any("GUIDE.en.md" in error for error in errors), errors)

    def test_linked_translation_passes(self) -> None:
        self.fixture.write("README.md", "# README\n\n[реєстр](docs/DECISIONS.md), [настанова](docs/GUIDE.md)\n")
        self.fixture.write("docs/GUIDE.md", "# Настанова\n\n[English](GUIDE.en.md)\n")
        self.fixture.write("docs/GUIDE.en.md", "# Guide\n")
        self.assertEqual(self.errors(), [])

    def test_code_directory_readme_is_out_of_scope(self) -> None:
        """A README inside a code tree documents that directory, not the project."""
        self.fixture.write("wsm/README.md", "# Пакети\n")
        self.assertEqual(self.errors(), [])

    def test_repository_itself_passes(self) -> None:
        self.assertEqual(checker.check(ROOT), [])


if __name__ == "__main__":
    unittest.main()
