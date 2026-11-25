# SPDX-License-Identifier: LicenseRef-Volnist
"""Source-contract checks for the WSM Qt/QML preview frontend.

These checks do not replace a Qt build, Guix package build, or live ISO test.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "installer" / "gui"


class InstallerGuiContractTests(unittest.TestCase):
    def test_qml_frontend_and_kde_launcher_exist(self) -> None:
        self.assertTrue((GUI / "CMakeLists.txt").is_file())
        self.assertTrue((GUI / "qml" / "Main.qml").is_file())
        self.assertTrue((GUI / "assets" / "wsm-installer.desktop").is_file())
        qml = (GUI / "qml" / "Main.qml").read_text(encoding="utf-8")
        desktop = (GUI / "assets" / "wsm-installer.desktop").read_text(encoding="utf-8")
        for label in ("Обладнання", "Накопичувачі", "Параметри", "Підсумковий перегляд"):
            self.assertIn(label, qml)
        self.assertIn("Exec=wsm-installer", desktop)
        self.assertIn("Name[uk]=Інсталятор WSM", desktop)
        self.assertIn("Icon=wsm-installer", desktop)
        self.assertTrue((GUI / "assets" / "wsm-installer.svg").is_file())

    def test_backend_handoff_uses_argument_vector_not_a_shell(self) -> None:
        source = (GUI / "src" / "PreflightController.cpp").read_text(encoding="utf-8")
        self.assertIn("process->start(program, arguments);", source)
        self.assertIn('QStringLiteral("wsm_hwcheck")', source)
        self.assertIn('QStringLiteral("--compact")', source)
        self.assertIn('QStringLiteral("wsm_install")', source)
        self.assertIn('QStringLiteral("--preflight")', source)
        self.assertIn('QStringLiteral("--backend")', source)
        self.assertIn('QStringLiteral("guix")', source)
        self.assertNotIn('QStringLiteral("--quiet")', source)
        self.assertIn('QStringLiteral("BLOCKED:")', source)
        self.assertNotIn("QProcess::execute", source)
        self.assertNotIn("system(", source)
        self.assertNotIn("popen(", source)
        self.assertNotIn("bash -c", source)

    def test_storage_inventory_is_read_only_and_selection_is_ephemeral(self) -> None:
        source = (GUI / "src" / "PreflightController.cpp").read_text(encoding="utf-8")
        qml = (GUI / "qml" / "Main.qml").read_text(encoding="utf-8")
        for argument in ("--json", "--bytes", "--tree",
                         "NAME,MODEL,SIZE,TYPE,TRAN,RO,RM,PATH"):
            self.assertIn(argument, source)
        self.assertIn("void PreflightController::selectDisk", source)
        self.assertIn("m_selectedDisk = devicePath", source)
        self.assertIn("в пам’яті UI", qml)
        self.assertIn("WSM_LSBLK_EXECUTABLE", source)
        forbidden = ("mkfs", "parted", "sfdisk", "sgdisk", "wipefs",
                     "grub-install", "guix system init")
        for command in forbidden:
            self.assertNotIn(command, source)
            self.assertNotIn(command, qml)

    def test_diagnostic_only_boundary_is_visible(self) -> None:
        qml = (GUI / "qml" / "Main.qml").read_text(encoding="utf-8")
        readme = (GUI / "README.md").read_text(encoding="utf-8")
        self.assertIn("diagnostic-only", qml)
        self.assertIn("Підтвердити лише перегляд", qml)
        self.assertIn("Жодна зміна диска не відбудеться", qml)
        self.assertIn("не проходив CMake/Qt compilation", readme)

    def test_guix_runtime_paths_are_supplied_to_python_processes(self) -> None:
        source = (GUI / "src" / "PreflightController.cpp").read_text(encoding="utf-8")
        package = (ROOT / "wsm" / "packages" / "installer.scm").read_text(encoding="utf-8")
        self.assertIn("WSM_GUIX_PYTHONPATH", source)
        self.assertIn("GUIX_PYTHONPATH", source)
        self.assertIn("setProcessEnvironment", source)
        self.assertIn("WSM_GUIX_PYTHONPATH", package)
        self.assertIn("WSM_PYTHON_EXECUTABLE", package)

    def test_package_is_separate_from_live_iso_recipe(self) -> None:
        package = (ROOT / "wsm" / "packages" / "installer.scm").read_text(encoding="utf-8")
        self.assertIn("(define-public wsm-installer", package)
        self.assertIn("(wsm packages wsm)", package)
        self.assertIn("(license #f)", package)
        self.assertIn("qtdeclarative", package)
        self.assertNotIn("qtquickcontrols2", package)
        self.assertIn("(inputs (list qtbase qtdeclarative))", package)
        self.assertIn("util-linux", package)
        self.assertIn("WSM_GUIX_PYTHONPATH", package)
        self.assertIn("WSM_LSBLK_EXECUTABLE", package)
        self.assertNotIn("systems/live.scm", package)
        self.assertNotIn("scripts/build_iso.sh", package)
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("check-installer-gui", makefile)
        self.assertIn("check: check-installer-gui", makefile)

    def test_process_execution_is_bounded_and_fail_closed(self) -> None:
        source = (GUI / "src" / "PreflightController.cpp").read_text(encoding="utf-8")
        header = (GUI / "src" / "PreflightController.h").read_text(encoding="utf-8")
        self.assertIn("m_processTimedOut", header)
        self.assertIn("60000", source)
        self.assertIn("30000", source)
        self.assertIn("10000", source)
        self.assertIn("process->terminate()", source)
        self.assertIn("process->kill()", source)
        self.assertIn("kMaximumStdoutBytes", source)
        self.assertIn("kMaximumStderrBytes", source)
        self.assertIn("validateDiagnosticPlan", source)
        self.assertIn('{"dry_run", true}', source)
        self.assertIn('{"plan_confirmable", false}', source)
        self.assertIn('{"mutations_authorized", false}', source)
        self.assertIn('{"backend_invoked", false}', source)
        self.assertIn('{"disk_access_performed", false}', source)
        self.assertIn("plan_sha256", source)
        self.assertIn("diagnostic-only", source)
        self.assertIn('QStringLiteral("plan_version")', source)
        self.assertIn('QStringLiteral("plan_mode")', source)
        self.assertIn('QStringLiteral("source_report")', source)
        self.assertIn("QCryptographicHash::hash(m_reportBytes", source)
        self.assertIn("unhashedPlan.remove", source)
        self.assertIn("QJsonDocument::Compact", source)

    def test_qml_smoke_mode_does_not_probe_hardware(self) -> None:
        main = (GUI / "src" / "main.cpp").read_text(encoding="utf-8")
        qml = (GUI / "qml" / "Main.qml").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "installer-gui.yml").read_text(encoding="utf-8")
        self.assertIn("smoke-test", main)
        self.assertIn("wsmSmokeTest", main)
        self.assertIn("if (!wsmSmokeTest)", qml)
        self.assertIn("--smoke-test", workflow)
        self.assertNotIn("timeout --kill-after", workflow)

    def test_qml_navigation_uses_observable_controller_state(self) -> None:
        qml = (GUI / "qml" / "Main.qml").read_text(encoding="utf-8")
        header = (GUI / "src" / "PreflightController.h").read_text(encoding="utf-8")
        controller = (GUI / "src" / "PreflightController.cpp").read_text(encoding="utf-8")
        policy = (GUI / "src" / "InstallerWorkflowPolicy.cpp").read_text(encoding="utf-8")
        tests = (GUI / "tests" / "tst_installer_workflow_policy.cpp").read_text(encoding="utf-8")
        self.assertIn("readonly property var workflowState", qml)
        self.assertIn("wsmController.canEnterStep(step)", qml)
        self.assertIn("diskInventoryState", header)
        self.assertIn("Q_INVOKABLE bool canEnterStep(int step) const", header)
        self.assertIn("InstallerWorkflowPolicy::canEnterStep", controller)
        self.assertIn('QStringLiteral("loading")', controller)
        self.assertIn('QStringLiteral("unavailable")', controller)
        self.assertIn('QStringLiteral("loaded")', controller)
        self.assertIn('step == 3 || step == 4', policy)
        self.assertIn("choicesAndReviewRequireCompletedDiskInventory", tests)
        self.assertIn("enabled: root.canOpenStep(index)", qml)
        self.assertIn("root.canOpenStep(root.currentStep + 1)", qml)
        self.assertIn("Qt.quit()", qml)

    def test_behavioral_policy_is_built_and_executed_in_ci(self) -> None:
        cmake = (GUI / "CMakeLists.txt").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "installer-gui.yml").read_text(encoding="utf-8")
        self.assertIn("WSM_BUILD_TESTS", cmake)
        self.assertIn("Qt6::Test", cmake)
        self.assertIn("installer-workflow-policy", cmake)
        self.assertIn("-DWSM_BUILD_TESTS=ON", workflow)
        self.assertIn("ctest --test-dir build/wsm-installer", workflow)

    def test_installer_workflow_respects_ci_queue_policy(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "installer-gui.yml").read_text(encoding="utf-8")
        self.assertIn("push:", workflow)
        self.assertIn("branches:\n      - main", workflow)
        self.assertIn("concurrency:", workflow)
        self.assertIn("cancel-in-progress: true", workflow)

    def test_guix_package_expression_has_balanced_parentheses(self) -> None:
        source = (ROOT / "wsm" / "packages" / "installer.scm").read_text(encoding="utf-8")
        depth = 0
        in_string = False
        escaped = False
        for line in source.splitlines():
            for character in line:
                if in_string:
                    if escaped:
                        escaped = False
                    elif character == chr(92):
                        escaped = True
                    elif character == '"':
                        in_string = False
                elif character == ";":
                    break
                elif character == '"':
                    in_string = True
                elif character == "(":
                    depth += 1
                elif character == ")":
                    depth -= 1
                    self.assertGreaterEqual(depth, 0)
        self.assertFalse(in_string)
        self.assertEqual(depth, 0)


if __name__ == "__main__":
    unittest.main()
