# SPDX-License-Identifier: GPL-3.0-or-later

PYTHON ?= python3
GUIX ?= guix

.PHONY: check check-docs check-hardware-schema check-hwcheck check-installer check-release check-qemu-harness check-validation-protocols check-hardware-providers check-minimal-system check-uefi-preboot-policy check-profiles check-syntax check-state check-isa check-live-acceptance check-profiles-matrix check-perf-baseline check-profile-evidence check-profile-match check-release-verdict check-makefile check-system vm-system vm-system-serial describe-lock check-locked-system release-bundle

check: check-docs check-hardware-schema check-hwcheck check-installer check-release check-qemu-harness check-validation-protocols check-hardware-providers check-minimal-system check-uefi-preboot-policy check-profiles check-syntax check-state check-isa check-live-acceptance check-profiles-matrix check-perf-baseline check-profile-evidence check-profile-match check-release-verdict check-makefile

check-profiles:
	$(PYTHON) tests/test_system_profiles.py

check-syntax:
	$(PYTHON) tests/test_python_syntax.py

check-state:
	$(PYTHON) tests/test_state_ownership.py

check-isa:
	$(PYTHON) tests/test_cpu_isa.py

check-live-acceptance:
	$(PYTHON) tests/test_live_iso_acceptance.py

check-perf-baseline:
	$(PYTHON) tests/test_perf_baseline.py

check-profile-evidence:
	$(PYTHON) tests/test_profile_evidence.py
	$(PYTHON) scripts/check_profile_evidence.py

check-profile-match:
	$(PYTHON) tests/test_profile_match.py

check-release-verdict:
	$(PYTHON) tests/test_verify_live_release.py

check-makefile:
	$(PYTHON) tests/test_makefile_coverage.py

check-profiles-matrix:
	$(PYTHON) tests/test_profiles.py

check-docs:
	$(PYTHON) scripts/check_docs.py

check-system:
	$(GUIX) system build systems/minimal.scm

vm-system:
	$(GUIX) system vm systems/minimal.scm

vm-system-serial:
	$(GUIX) system vm --no-graphic systems/minimal.scm

check-hardware-schema:
	$(PYTHON) tests/test_hardware_report.py

check-hwcheck:
	$(PYTHON) tests/test_hwcheck.py

check-installer:
	$(PYTHON) tests/test_backend_guix.py
	$(PYTHON) tests/test_guix_deploy_cli.py
	$(PYTHON) tests/test_install_preflight.py
	$(PYTHON) tests/test_install_preflight_acceptance.py
	$(PYTHON) tests/test_installer_freshness.py

check-qemu-harness:
	$(PYTHON) tests/test_qemu_boot_smoke.py
	$(PYTHON) -m unittest discover -s tests -p 'test_qemu_hwcheck_guest.py' -v

check-validation-protocols:
	$(PYTHON) tests/test_validation_protocol_privacy.py
	$(PYTHON) tests/test_pcie_link_health_protocol.py

check-hardware-providers:
	$(PYTHON) tests/test_hardware_provider_addendum.py

check-minimal-system:
	$(PYTHON) tests/test_minimal_system.py

check-uefi-preboot-policy:
	$(PYTHON) tests/test_uefi_preboot_probe_policy.py

check-release:
	$(PYTHON) tests/test_release_artifacts.py

describe-lock:
	$(GUIX) time-machine -C channels.lock.scm -- describe -f channels

check-locked-system:
	$(GUIX) time-machine -C channels.lock.scm -- system build systems/minimal.scm

release-bundle: check
	$(PYTHON) scripts/build_release_bundle.py
