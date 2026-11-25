# SPDX-License-Identifier: GPL-3.0-or-later

PYTHON ?= python3
GUIX ?= guix

.PHONY: check check-docs check-hardware-schema check-hwcheck check-installer check-qemu-harness check-validation-protocols check-system vm-system

check: check-docs check-hardware-schema check-hwcheck check-installer check-qemu-harness check-validation-protocols

check-docs:
	$(PYTHON) scripts/check_docs.py

check-system:
	$(GUIX) system build systems/minimal.scm

vm-system:
	$(GUIX) system vm systems/minimal.scm

check-hardware-schema:
	$(PYTHON) tests/test_hardware_report.py

check-hwcheck:
	$(PYTHON) tests/test_hwcheck.py

check-installer:
	$(PYTHON) tests/test_install_preflight.py
	$(PYTHON) tests/test_install_preflight_acceptance.py
	$(PYTHON) tests/test_installer_freshness.py

check-qemu-harness:
	$(PYTHON) tests/test_qemu_boot_smoke.py
	$(PYTHON) -m unittest discover -s tests -p 'test_qemu_hwcheck_guest.py' -v

check-validation-protocols:
	$(PYTHON) tests/test_validation_protocol_privacy.py
