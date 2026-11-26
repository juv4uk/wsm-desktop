# SPDX-License-Identifier: LicenseRef-Volnist
"""The Calamares jobmodule must fail closed and stay thin.

Calamares injects ``libcalamares`` at runtime, so these tests substitute a fake
module with the same shape. That is the only way to test a jobmodule without a
running installer, and it keeps the module's contract honest: ``None`` on
success, ``(message, details)`` on failure, never a silent pass.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "installer" / "calamares" / "modules" / "wsm_deploy" / "main.py"
GIB = 1024 ** 3


class FakeStorage:
    def __init__(self, values: dict) -> None:
        self.values = values

    def value(self, key):
        return self.values.get(key)


def install_fake_libcalamares(values: dict) -> None:
    module = types.ModuleType("libcalamares")
    module.globalstorage = FakeStorage(values)
    module.utils = types.SimpleNamespace(debug=lambda message: None)
    sys.modules["libcalamares"] = module


def load_module():
    spec = importlib.util.spec_from_file_location("wsm_deploy_main", MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def report_file(directory: Path) -> Path:
    source = ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json"
    target = directory / "report.json"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


class DescriptorTests(unittest.TestCase):
    def test_module_desc_declares_a_python_job(self) -> None:
        import yaml

        desc = yaml.safe_load(
            (MODULE.parent / "module.desc").read_text(encoding="utf-8")
        )
        self.assertEqual(desc["name"], "wsm_deploy")
        self.assertEqual(desc["interface"], "python")
        self.assertEqual(desc["script"], "main.py")
        self.assertTrue(desc["required"])


class FailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()
        sys.modules.pop("libcalamares", None)

    def test_missing_report_fails_closed(self) -> None:
        install_fake_libcalamares({"wsmTargetDisk": "/dev/nvme0n1", "wsmTargetSizeBytes": 256 * GIB, "wsmDryRun": True})
        result = load_module().run()
        self.assertIsNotNone(result)
        message, details = result
        self.assertIn("report", message.lower())
        self.assertIn("unverified hardware", details)

    def test_missing_disk_is_refused(self) -> None:
        """WSM never chooses a disk for the user."""
        report = report_file(self.directory)
        install_fake_libcalamares({"wsmReportPath": str(report), "wsmTargetSizeBytes": 256 * GIB, "wsmDryRun": True})
        result = load_module().run()
        self.assertIsNotNone(result)
        self.assertIn("disk", result[0].lower())

    def test_missing_size_is_refused(self) -> None:
        report = report_file(self.directory)
        install_fake_libcalamares({"wsmReportPath": str(report), "wsmTargetDisk": "/dev/nvme0n1", "wsmDryRun": True})
        result = load_module().run()
        self.assertIsNotNone(result)
        self.assertIn("size", result[0].lower())

    def test_invalid_evidence_blocks_deployment(self) -> None:
        report = report_file(self.directory)
        evidence = self.directory / "evidence.json"
        evidence.write_text(json.dumps({
            "schema": "wsm-profile-evidence/1",
            "profile": {"vendor": "Gigabyte", "model": "GA-H170-Gaming3",
                        "slug": "gigabyte/ga-h170-gaming3"},
            "report_id": "0f3c9a1e-2b44-4c8d-9f10-77a1b2c3d4e5",
            "report_schema_version": "1.0.0",
            "isa_level": "x86-64-v3",
            "verified_on": "2026-11-26",
            "verified_by": "автори проєкту",
            "verified_functions": [{"name": "graphics", "status": "not-assessed"}],
            "known_limitations": [],
            "not_assessed": ["suspend"],
        }), encoding="utf-8")
        install_fake_libcalamares({
            "wsmReportPath": str(report),
            "wsmTargetDisk": "/dev/nvme0n1",
            "wsmTargetSizeBytes": 256 * GIB,
            "wsmDryRun": True,
            "wsmProfileEvidence": str(evidence),
        })
        result = load_module().run()
        self.assertIsNotNone(result)
        self.assertIn("evidence", result[0].lower())


class PreviewOutcomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.report = report_file(self.directory)

    def tearDown(self) -> None:
        self.temporary.cleanup()
        sys.modules.pop("libcalamares", None)

    def values(self, **extra):
        return {
            "wsmReportPath": str(self.report),
            "wsmTargetDisk": "/dev/nvme0n1",
            "wsmTargetSizeBytes": 256 * GIB,
            **extra,
        }

    def test_explicit_preview_returns_non_success_not_none(self) -> None:
        from unittest.mock import patch

        install_fake_libcalamares(self.values(wsmDryRun=True))
        with patch("wsm_install.executor.execute", return_value=[] ) as execute:
            result = load_module().run()
        self.assertIsNotNone(result)
        self.assertIn("not installed", result[0].lower())
        execute.assert_called_once()
        self.assertIs(execute.call_args.kwargs["dry_run"], True)
        self.assertNotIn("acknowledgement", execute.call_args.kwargs)

    def test_explicit_false_dry_run_is_refused_before_preview(self) -> None:
        from unittest.mock import patch

        install_fake_libcalamares(self.values(wsmDryRun=False))
        with patch("wsm_install.executor.execute") as execute:
            result = load_module().run()
        self.assertIsNotNone(result)
        self.assertIn("APPLY is disabled", result[0])
        execute.assert_not_called()

    def test_missing_dry_run_is_refused_not_success(self) -> None:
        from unittest.mock import patch

        install_fake_libcalamares(self.values())
        with patch("wsm_install.executor.execute") as execute:
            result = load_module().run()
        self.assertIsNotNone(result)
        self.assertIn("APPLY is disabled", result[0])
        execute.assert_not_called()

    def test_pretty_name_is_defined(self) -> None:
        install_fake_libcalamares({})
        self.assertTrue(load_module().pretty_name())


if __name__ == "__main__":
    unittest.main()
