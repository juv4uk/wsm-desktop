# SPDX-License-Identifier: LicenseRef-Volnist
"""Static safety contract for the WSM PySide6/Kirigami preview UI."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "wsm_installer"


class InstallerGuiContractTests(unittest.TestCase):
    def test_gui_uses_kirigami_and_typed_controller(self) -> None:
        qml = (GUI / "qml" / "Main.qml").read_text(encoding="utf-8")
        controller = (GUI / "controller.py").read_text(encoding="utf-8")
        app = (GUI / "app.py").read_text(encoding="utf-8")
        self.assertIn("org.kde.kirigami", qml)
        self.assertIn("wsmController", qml)
        self.assertIn("class PreviewController(QObject)", controller)
        self.assertIn("QQmlApplicationEngine", app)
        self.assertIn("--smoke-test", app)

    def test_ui_has_no_apply_or_command_execution_api(self) -> None:
        source = "\n".join(
            (GUI / name).read_text(encoding="utf-8")
            for name in ("controller.py", "preview.py", "app.py")
        )
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse(any(alias.name == "subprocess" for alias in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "subprocess")
            elif isinstance(node, ast.Call):
                function = node.func
                self.assertFalse(isinstance(function, ast.Name) and function.id in {"exec", "eval"})
                self.assertFalse(
                    isinstance(function, ast.Attribute)
                    and function.attr in {"system", "popen", "Popen"}
                )
        self.assertNotIn("shell=True", source)
        self.assertNotIn("guix system init", source)
        self.assertNotIn("QProcess", source)
        self.assertIn("mutations_authorized", (GUI / "qml" / "Main.qml").read_text(encoding="utf-8"))

    def test_qml_keeps_unknown_states_visible_and_free_of_fake_green_status(self) -> None:
        qml = (GUI / "qml" / "Main.qml").read_text(encoding="utf-8")
        self.assertIn("discoveryStatus", qml)
        self.assertIn("driverStatus", qml)
        self.assertIn("firmwareStatus", qml)
        self.assertNotIn("fully-supported", qml)
        self.assertNotIn("fully_supported", qml)

    def test_scroll_views_use_the_aliased_controls_module(self) -> None:
        qml = (GUI / "qml" / "Main.qml").read_text(encoding="utf-8")
        self.assertIn("import QtQuick.Controls as Controls", qml)
        self.assertNotRegex(qml, String.raw`(?m)^\s*ScrollView\s*\{`)
        self.assertEqual(qml.count("Controls.ScrollView {"), 3)

    def test_package_recipe_returns_value_for_guix_build_f(self) -> None:
        recipe = (ROOT / "wsm" / "packages" / "installer.scm").read_text(encoding="utf-8")
        # Guix `build -f` requires the file's final expression to yield a package.
        self.assertEqual(recipe.rstrip().splitlines()[-1], "wsm-installer")

    def test_guix_smoke_uses_the_installed_optional_package(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        target = makefile.split("check-installer-gui-guix:", 1)[1]
        self.assertIn("shell -L . -f wsm/packages/installer.scm", target)
        self.assertIn("env -u PYTHONPATH", target)
        self.assertIn("wsm-installer --smoke-test", target)
        self.assertIn('"${QML_IMPORT_PATH}"', target)
        self.assertIn('"${QT_PLUGIN_PATH}"', target)
        self.assertIn("tests/guix/installer_navigation.py", target)
        self.assertNotIn("PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 -m wsm_installer --smoke-test", target)

    def test_minimal_live_definitions_do_not_gain_qt_dependencies(self) -> None:
        live_minimal = (ROOT / "systems" / "live-minimal.scm").read_text(encoding="utf-8")
        self.assertNotIn("wsm-installer", live_minimal)
        self.assertNotIn("python-pyside-6", live_minimal)
