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

from scripts.qemu_boot_smoke import BoundedProcessResult
from scripts.ci_probe_qemu_cxl import (
    MAX_CAPTURE_BYTES,
    build_qemu_command,
    parse_kernel_config,
    run_qemu_topology_probe,
)



def bounded_result(stdout: str, stderr: str = "", returncode: int = 0, *, timed_out: bool = False, truncated: bool = False) -> BoundedProcessResult:
    stdout_bytes = stdout.encode("utf-8")
    stderr_bytes = stderr.encode("utf-8")
    return BoundedProcessResult(
        returncode,
        timed_out,
        stdout_bytes[-(56 * 1024):],
        stderr_bytes[-(8 * 1024):],
        len(stdout_bytes),
        len(stderr_bytes),
        truncated or len(stdout_bytes) > 56 * 1024,
        truncated or len(stderr_bytes) > 8 * 1024,
        False,
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
        self.assertIn("-S", command)
        self.assertNotIn("-drive", command)
        self.assertNotIn("-cdrom", command)
        self.assertNotIn("-nic", command)
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
        with patch("scripts.ci_probe_qemu_cxl.run_bounded_process", return_value=bounded_result(completed.stdout, completed.stderr)) as reader:
            result = run_qemu_topology_probe("qemu")
        self.assertEqual(reader.call_args.kwargs["stdin_bytes"], b"info qtree\\ninfo pci\\nquit\\n")
        self.assertEqual(reader.call_args.kwargs["max_stdout_bytes"] + reader.call_args.kwargs["max_stderr_bytes"], MAX_CAPTURE_BYTES)
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
        with patch("scripts.ci_probe_qemu_cxl.run_bounded_process", return_value=bounded_result(completed.stdout, completed.stderr, completed.returncode)):
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
        with patch("scripts.ci_probe_qemu_cxl.run_bounded_process", return_value=bounded_result(completed.stdout, completed.stderr, completed.returncode)):
            result = run_qemu_topology_probe("qemu")
        self.assertEqual(result["status"], "cxl-device-or-machine-unsupported")

    def test_qemu_topology_probe_rejects_streams_over_capture_budget(self) -> None:
        captured = bounded_result("x" * (64 * 1024 + 1), truncated=True)
        with patch("scripts.ci_probe_qemu_cxl.run_bounded_process", return_value=captured):
            result = run_qemu_topology_probe("qemu")
        self.assertEqual(result["status"], "output-limit-exceeded")
        self.assertEqual(result["devices_seen"], [])

    def test_qemu_topology_probe_reports_timeout_from_bounded_reader(self) -> None:
        captured = bounded_result("", timed_out=True)
        with patch("scripts.ci_probe_qemu_cxl.run_bounded_process", return_value=captured):
            result = run_qemu_topology_probe("qemu")
        self.assertEqual(result["status"], "timeout")

    def test_qemu_command_does_not_claim_guest_or_hardware_compatibility(self) -> None:
        # The probe instantiates QEMU objects while guest CPUs are paused; it
        # intentionally makes no claim about Linux discovery or physical CXL.
        command = build_qemu_command("qemu-system-x86_64")
        self.assertEqual(command[command.index("-S")], "-S")


if __name__ == "__main__":
    unittest.main()
