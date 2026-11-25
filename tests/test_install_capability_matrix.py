"""Policy invariants for the installer capability matrix.

These tests validate documentation guardrails only. They do not prove hardware
functionality and do not replace the disposable-QEMU tests in issue #14.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "INSTALL-CAPABILITY-MATRIX.md"


class InstallerCapabilityMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = MATRIX.read_text(encoding="utf-8")
        cls.lower = cls.text.casefold()

    def test_all_four_install_scenarios_are_defined(self):
        for heading in (
            "4.1 локальна інтерактивна інсталяція",
            "4.2 offline-інсталяція",
            "4.3 network-assisted інсталяція",
            "4.4 headless / remote install",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, self.lower)

    def test_evidence_levels_are_not_collapsed(self):
        for term in (
            "discovered",
            "driver-bound",
            "firmware evidence",
            "functional test",
            "user-confirmed path",
        ):
            with self.subTest(term=term):
                self.assertIn(term, self.lower)

    def test_missing_coverage_remains_unknown_not_ready(self):
        self.assertIn("not-collected", self.lower)
        self.assertIn("unknown/not-collected", self.lower)
        self.assertIn("відсутній record не можна трактувати", self.lower)
        self.assertIn("не повинен виводити", self.lower)

    def test_storage_target_requires_user_selection_and_revalidation(self):
        self.assertIn("користувач окремо вибирає ціль", self.lower)
        self.assertIn("перевіряється повторно", self.lower)
        self.assertIn("не вибирати «перший диск»", self.lower)
        self.assertIn("confirmation invalidated", self.lower)

    def test_offline_path_does_not_require_network(self):
        offline = self.lower.split("### 4.2 offline-інсталяція", 1)[1].split(
            "### 4.3 network-assisted інсталяція", 1
        )[0]
        self.assertIn("не є обов'язковою умовою", offline)
        self.assertIn("не blocker", offline)
        self.assertIn("відсутність мережі", offline)

    def test_network_assisted_requires_separate_connectivity_evidence(self):
        network = self.lower.split("### 4.3 network-assisted інсталяція", 1)[1].split(
            "### 4.4 headless / remote install", 1
        )[0]
        self.assertIn("network connectivity", network)
        self.assertIn("read-only connectivity test", network)
        self.assertIn("не доводять доступність конкретного сервера", network)

    def test_headless_requires_an_explicit_control_path(self):
        headless = self.lower.split("### 4.4 headless / remote install", 1)[1].split(
            "## 5.", 1
        )[0]
        self.assertIn("перевірений канал керування", headless)
        self.assertIn("unsupported/unknown", headless)

    def test_firmware_availability_is_split_by_deployment_stage(self):
        firmware = self.lower.split("## 6. firmware", 1)[1].split("## 7.", 1)[0]
        for term in ("live image", "initrd", "цільовій системі"):
            with self.subTest(term=term):
                self.assertIn(term, firmware)

    def test_qemu_policy_excludes_host_block_device_passthrough(self):
        self.assertIn("без host block-device passthrough", self.lower)
        self.assertIn("synthetic fixtures", self.lower)


if __name__ == "__main__":
    unittest.main()
