# SPDX-License-Identifier: LicenseRef-Volnist
"""A test that unittest never collects is not a test.

This file exists because of a real defect: `tests/test_docs.py` ended up with two
classes named `DocumentationLanguageTests`. Python keeps only the last one, so
four tests — including the ones checking the Ukrainian-language rule — sat in the
file, looked green in review, and never ran.

The repository already refuses "coverage by filename mention" in the Omarchy
register. The same standard applies to tests themselves: a `def test_...` that
unittest cannot see proves nothing.

So for every test module this file compares what is written with what unittest
collects, and reports the difference.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"


def test_modules() -> list[Path]:
    return sorted(TESTS.glob("test_*.py"))


def declared_tests(source: Path) -> tuple[dict[str, set[str]], list[str]]:
    """Test methods written in the file, plus class names defined more than once."""
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    declared: dict[str, set[str]] = {}
    duplicates: list[str] = []
    seen: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name in seen:
            duplicates.append(node.name)
        seen.add(node.name)
        methods = {
            item.name
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name.startswith("test")
        }
        if methods:
            declared[node.name] = methods
    return declared, duplicates


def load_module(source: Path):
    name = f"registration_{source.stem}"
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def collected_tests(module) -> dict[str, set[str]]:
    """Test methods unittest would actually run for this module."""
    collected: dict[str, set[str]] = {}
    loader = unittest.TestLoader()
    for attribute in dir(module):
        value = getattr(module, attribute)
        if not (isinstance(value, type) and issubclass(value, unittest.TestCase)):
            continue
        if value.__module__ != module.__name__:
            continue
        names = {
            test_id.split(".")[-1]
            for test_id in loader.getTestCaseNames(value)
        }
        if names:
            collected[attribute] = names
    return collected


class TestRegistrationTests(unittest.TestCase):
    def test_every_declared_test_is_collected(self) -> None:
        problems: list[str] = []
        for source in test_modules():
            declared, duplicates = declared_tests(source)
            for name in duplicates:
                problems.append(
                    f"{source.relative_to(ROOT)}: class {name!r} is defined twice; "
                    f"the first definition and its tests are unreachable"
                )
            if not declared:
                continue
            module = load_module(source)
            collected = collected_tests(module)
            for class_name, methods in declared.items():
                found = collected.get(class_name, set())
                missing = methods - found
                if missing:
                    problems.append(
                        f"{source.relative_to(ROOT)}: {class_name}: unittest does not "
                        f"collect {sorted(missing)}"
                    )
        self.assertEqual(problems, [], "\n".join(problems))

    def test_the_rule_catches_a_shadowed_class(self) -> None:
        """The detector must be red on the exact defect it was written for."""
        sample = (
            "import unittest\n"
            "class GateTests(unittest.TestCase):\n"
            "    def test_first(self):\n"
            "        pass\n"
            "class GateTests(unittest.TestCase):\n"
            "    def test_second(self):\n"
            "        pass\n"
        )
        with self.subTest("duplicate class is reported"):
            path = TESTS / "_tmp_duplicate_sample.py"
            path.write_text(sample, encoding="utf-8")
            try:
                _, duplicates = declared_tests(path)
            finally:
                path.unlink()
            self.assertEqual(duplicates, ["GateTests"])


if __name__ == "__main__":
    unittest.main()
