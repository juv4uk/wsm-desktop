# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the read-only QEMU CXL feasibility probe."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci_probe_qemu_cxl import (
    build_qemu_command,
    parse_kernel_config,
    run_qemu_topology_probe,
)


class QemuCxlProbeTests(unittest.TestCase):
    def test_kernel_config_keeps_y_m_n_and_unknown_distinct(self) -> None:
        parsed = parse_kernel_config(
            'CONFIG_CXL_BUS=y\n'
            'CONFIG_CXL_PCI=m\n'
            '# CONFIG_CXL_PMEM is not set\n'
        )
        self.assertEqual(parsed["CONFIG_CXL_BUS"], "y")
        self.assertEqual(parsed["CONFIG_CXL_PCI"], "m")
        self.assertEqual(parsed["CONFIG_CXL_PMEM"], "n")
        self.assertNotIn("CONFIG_CXL_ACPI", parsed)

    def test_qemu_topology_uses_only_volatile_memory_and_no_host_io(self) -> None:
        command = build_qemu_command("qemu-system-x86_64")
        self.assertIn("q35,cxl=on", command)
        self.assertIn("cxl-type3,bus=root_port0,volatile-memdev=vmem0,id=cxl-vmem0", command)
        self.assertIn("-nodefaults", command)
        self.assertIn("-no-user-config", command)
        self.assertIn("-S", command)
        self.assertNotIn("-drive", command)
        self.assertNotIn("-cdrom", command)
        self.assertIn("-nic", command)
        self.assertEqual(command[command.index("-nic") + 1], "none")
        self.assertIn("-serial", command)
        self.assertEqual(command[command.index("-serial") + 1], "none")
        self.assertNotIn("-netdev", command)
        self.assertFalse(any("host=" in token for token in command))
        self.assertFalse(any("serial=" in token.casefold() for token in command))
        self.assertIn("-monitor", command)
        self.assertEqual(command[command.index("-monitor") + 1], "stdio")

    def test_qemu_topology_probe_requires_all_declared_device_ids(self) -> None:
        completed = type(
            "Completed",
            (),
            {
                "stdout": 'dev: pxb-cxl, id "cxl.1"\n'
                          'dev: cxl-rp, id "root_port0"\n'
                          'dev: cxl-type3, id "cxl-vmem0"\n',
                "stderr": "",
                "returncode": 0,
            },
        )()
        with patch("scripts.ci_probe_qemu_cxl.subprocess.run", return_value=completed):
            result = run_qemu_topology_probe("qemu")
        self.assertEqual(result["status"], "type3-topology-instantiated")
        self.assertEqual(result["devices_seen"], ["cxl.1", "root_port0", "cxl-vmem0"])

    def test_qemu_topology_probe_does_not_call_a_partial_tree_success(self) -> None:
        completed = type(
            "Completed",
            (),
            {
                "stdout": 'dev: pxb-cxl, id "cxl.1"\n',
                "stderr": "",
                "returncode": 0,
            },
        )()
        with patch("scripts.ci_probe_qemu_cxl.subprocess.run", return_value=completed):
            result = run_qemu_topology_probe("qemu")
        self.assertEqual(result["status"], "topology-probe-failed")

    def test_qemu_topology_probe_reports_explicit_unsupported_without_raising(self) -> None:
        completed = type(
            "Completed",
            (),
            {
                "stdout": "",
                "stderr": "Property 'CXL.cxl' not found",
                "returncode": 1,
            },
        )()
        with patch("scripts.ci_probe_qemu_cxl.subprocess.run", return_value=completed):
            result = run_qemu_topology_probe("qemu")
        self.assertEqual(result["status"], "cxl-device-or-machine-unsupported")

    def test_probe_does_not_return_raw_pci_or_resource_diagnostics(self) -> None:
        completed = type(
            "Completed",
            (),
            {
                "stdout": "\\n".join([
                    "dev: pxb-cxl, id cxl.1",
                    "dev: cxl-rp, id root_port0",
                    "dev: cxl-type3, id cxl-vmem0",
                    "Bus 00:02.0 BDF 0000:00:02.0 Memory at 0xf0000000",
                ]),
                "stderr": "synthetic PCI resource diagnostic",
                "returncode": 0,
            },
        )()
        with patch("scripts.ci_probe_qemu_cxl.subprocess.run", return_value=completed) as run:
            result = run_qemu_topology_probe("qemu")
        self.assertNotIn("0000:00:02.0", repr(result))
        self.assertNotIn("0xf0000000", repr(result))
        self.assertNotIn("synthetic PCI resource diagnostic", repr(result))
        self.assertIn("expected synthetic CXL qdev objects", result["diagnostic"])
        self.assertNotIn("info pci", run.call_args.kwargs["input"])
    def test_qemu_command_does_not_claim_guest_or_hardware_compatibility(self) -> None:
        # The probe instantiates QEMU objects while guest CPUs are paused; it
        # intentionally makes no claim about Linux discovery or physical CXL.
        command = build_qemu_command("qemu-system-x86_64")
        self.assertEqual(command[command.index("-S")], "-S")


if __name__ == "__main__":
    unittest.main()
