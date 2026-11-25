# SPDX-License-Identifier: LicenseRef-Volnist
"""Source-level safety checks for the first WSM Qt/QML GUI slice."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "installer" / "gui"


class InstallerGuiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = (GUI / "src" / "main.cpp").read_text(encoding="utf-8")
        self.qml = (GUI / "qml" / "Main.qml").read_text(encoding="utf-8")
        self.package = (
            ROOT / "wsm" / "packages" / "installer-gui.scm"
        ).read_text(encoding="utf-8")

    def test_gui_has_the_five_required_user_steps(self) -> None:
        for text in (
            "Вітаємо у WSM Desktop",
            "Апаратні докази",
            "Накопичувачі",
            "Параметри системи",
            "Підсумок попереднього перегляду",
        ):
            with self.subTest(text=text):
                self.assertIn(text, self.qml)

    def test_hardware_collection_and_plan_use_argument_vectors(self) -> None:
        self.assertIn('QStringLiteral("python3")', self.controller)
        self.assertIn('QStringLiteral("wsm_hwcheck")', self.controller)
        self.assertIn('QStringLiteral("wsm_install")', self.controller)
        self.assertIn('QStringLiteral("--dry-run")', self.controller)
        self.assertIn("m_process.setArguments(arguments)", self.controller)
        self.assertNotIn("system(", self.controller)
        self.assertNotIn("popen(", self.controller)
        self.assertNotIn("bash -c", self.controller)

    def test_storage_inventory_is_read_only(self) -> None:
        self.assertIn('QStringLiteral("lsblk")', self.controller)
        self.assertIn('QStringLiteral("--json")', self.controller)
        self.assertNotIn("parted", self.controller.lower())
        self.assertNotIn("mkfs", self.controller.lower())
        self.assertNotIn("wipefs", self.controller.lower())
        self.assertNotIn("guix system init", self.controller.lower())

    def test_review_never_authorizes_apply_or_disk_access(self) -> None:
        self.assertIn("backendInvoked", self.qml)
        self.assertIn("diskAccessPerformed", self.qml)
        self.assertIn("Diagnostic-only", self.controller)
        self.assertIn("Кнопки встановлення немає", self.qml)
        self.assertNotIn("guix system init", self.controller.lower())

    def test_custom_license_is_not_mislabeled_as_gpl(self) -> None:
        self.assertIn("(license #f)", self.package)
        self.assertNotIn("gpl3+", self.package)

    def test_qt6_qml_controls_use_the_qt_declarative_closure(self) -> None:
        self.assertIn("qtdeclarative", self.package)
        self.assertNotIn("qtquickcontrols2", self.package)


if __name__ == "__main__":
    unittest.main()
