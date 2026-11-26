# SPDX-License-Identifier: LicenseRef-Volnist
"""The classification summary has a schema, and the producer must satisfy it.

`wsm-hardware-classification/2` is emitted by the classifier and read by whoever
stores it. Every other versioned artifact in this repository is checked against a
schema; this one was not, so a change to the summary shape could ship silently.

The strongest test here is the first: it runs the real classifier and validates
its actual output. A schema that only agrees with hand-written fixtures proves
nothing about the code that produces the artifact.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install.classification import classify  # noqa: E402


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_classification", ROOT / "scripts" / "check_classification.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = load_checker()


def summary() -> dict:
    return classify({"devices": []})


class ClassificationSchemaTests(unittest.TestCase):
    def test_real_classifier_output_validates(self) -> None:
        self.assertEqual(checker.problems(summary()), [])

    def test_unknown_version_is_refused_by_name(self) -> None:
        document = copy.deepcopy(summary())
        document["schema"] = "wsm-hardware-classification/3"
        found = checker.problems(document)
        self.assertTrue(found)
        self.assertTrue(any("wsm-hardware-classification/3" in item for item in found), found)

    def test_counts_must_describe_the_listed_subsystems(self) -> None:
        document = copy.deepcopy(summary())
        document["counts"]["known"] = len(document["subsystems"])
        found = checker.problems(document)
        self.assertTrue(any("counts" in item for item in found), found)

    def test_duplicate_subsystem_is_refused(self) -> None:
        document = copy.deepcopy(summary())
        document["subsystems"].append(copy.deepcopy(document["subsystems"][0]))
        document["counts"]["unknown"] += 1
        found = checker.problems(document)
        self.assertTrue(any("more than once" in item for item in found), found)

    def test_extra_field_is_refused(self) -> None:
        document = copy.deepcopy(summary())
        document["installation_verdict"] = "go"
        found = checker.problems(document)
        self.assertTrue(any("installation_verdict" in item for item in found), found)

    def test_level_vocabulary_is_closed(self) -> None:
        document = copy.deepcopy(summary())
        document["subsystems"][0]["level"] = "probably-fine"
        found = checker.problems(document)
        self.assertTrue(found, "an invented level must not validate")


if __name__ == "__main__":
    unittest.main()
