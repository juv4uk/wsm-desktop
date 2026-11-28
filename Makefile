# SPDX-License-Identifier: LicenseRef-Volnist

PYTHON ?= python3
QEMU_PYTHON ?= python3.11
GUIX ?= guix
PRODUCT ?= free



.PHONY: check-driver-profiles check check-ci-policy qemu-acceptance-manual check-guix-eval check-compatibility-eval release-gate describe-compatibility-lock build-compatibility-system image-live-compat check-docs check-doc-ownership check-regression-register check-release-info check-artifact-versions check-hardware-schema check-hwcheck check-installer check-release check-qemu-harness check-validation-protocols check-hardware-providers check-minimal-system check-uefi-preboot-policy check-system vm-system vm-system-serial describe-lock check-locked-system release-bundle check-profiles check-agent check-calamares check-channels check-cli-install check-env-preflight check-evidence-drafter check-executor check-tool-closure check-guided check-hygiene check-install-steps check-isa check-journal check-live-acceptance check-makefile check-observation check-partition check-perf-baseline check-boot-profile check-profile-evidence check-profile-match check-profiles-matrix check-release-verdict check-state check-syntax check-tui check-licences image-live-minimal check-temp-paths check-test-registration check-release-assets check-classification check-classification-policy check-readme-stage check-classification-schema check-ci-parity check-scheme-imports check-no-sleep-readiness check-ci-failure-visibility check-tests check-gp107-reference check-channel-artifacts check-release-docs check-channel-contract check-release-readiness check-cuirass check-branch-freshness check-narinfo check-substitutes check-package-version check-guix-sign check-lean-closure check-fpc-package check-fpc-classify check-fpc-partition check-fpc-profile check-fpc-preflight check-fpc-cli check-fpc-manifest build-fpc-packages

check: check-ci-policy check-docs check-doc-ownership check-regression-register check-release-info check-artifact-versions check-hardware-schema check-hwcheck check-installer check-release check-qemu-harness check-validation-protocols check-hardware-providers check-minimal-system check-uefi-preboot-policy check-profiles check-syntax check-state check-isa check-live-acceptance check-profiles-matrix check-perf-baseline check-boot-profile check-profile-evidence check-driver-profiles check-profile-match check-release-verdict check-makefile check-evidence-drafter check-partition check-install-steps check-hygiene check-channels check-executor check-tool-closure check-cli-install check-calamares check-guided check-tui check-agent check-journal check-env-preflight check-observation check-licences check-temp-paths check-test-registration check-release-assets check-classification check-classification-policy check-readme-stage check-classification-schema check-ci-parity check-scheme-imports check-no-sleep-readiness check-ci-failure-visibility check-tests check-gp107-reference check-channel-artifacts check-release-docs check-channel-contract check-release-readiness check-cuirass check-branch-freshness check-narinfo check-substitutes check-package-version check-guix-sign check-lean-closure check-fpc-package check-fpc-classify check-fpc-partition check-fpc-profile check-fpc-preflight check-fpc-cli check-fpc-manifest

check-profiles:
	$(PYTHON) tests/test_system_profiles.py

check-syntax:
	$(PYTHON) tests/test_python_syntax.py

check-scheme-imports:
	$(PYTHON) scripts/check_scheme_imports.py
	$(PYTHON) tests/test_scheme_imports.py
	$(PYTHON) scripts/check_scheme_module_coverage.py
	$(PYTHON) tests/test_scheme_module_coverage.py

check-state:
	$(PYTHON) tests/test_state_ownership.py

check-isa:
	$(PYTHON) tests/test_cpu_isa.py

check-live-acceptance:
	$(PYTHON) tests/test_live_iso_acceptance.py

check-perf-baseline:
	$(PYTHON) tests/test_perf_baseline.py

check-boot-profile:
	$(PYTHON) tests/test_boot_profile.py

check-profile-evidence:
	$(PYTHON) tests/test_profile_evidence.py
	$(PYTHON) scripts/check_profile_evidence.py

check-driver-profiles:
	$(PYTHON) tests/test_driver_profiles.py

check-profile-match:
	$(PYTHON) tests/test_profile_match.py

check-release-verdict:
	$(PYTHON) tests/test_verify_live_release.py

check-release-assets:
	$(PYTHON) tests/test_verify_release_assets.py

check-makefile:
	$(PYTHON) tests/test_makefile_coverage.py

check-evidence-drafter:
	$(PYTHON) tests/test_draft_profile_evidence.py

check-partition:
	$(PYTHON) tests/test_partition.py

check-install-steps:
	$(PYTHON) tests/test_install_steps.py

check-executor:
	$(PYTHON) tests/test_executor.py

# Proves the closure checker's behaviour on throwaway roots. It cannot prove any
# image: `--root` on this host describes this host, and the image ships no /usr
# yet. Run `scripts/check_tool_closure.py --root <image root>` for that.
check-tool-closure:
	$(PYTHON) scripts/check_tool_closure.py --self-check

check-cli-install:
	$(PYTHON) tests/test_cli_install.py

check-calamares:
	$(PYTHON) tests/test_calamares_module.py

check-guided:
	$(PYTHON) tests/test_guided.py

check-tui:
	$(PYTHON) tests/test_tui.py

check-classification:
	$(PYTHON) tests/test_classification.py

check-ci-policy:
	$(PYTHON) tests/test_ci_acceptance_policy.py

check-agent:
	$(PYTHON) tests/test_agent.py

check-journal:
	$(PYTHON) tests/test_journal.py

check-env-preflight:
	$(PYTHON) tests/test_preflight_env.py

check-observation:
	$(PYTHON) tests/test_observation_principles.py

check-licences:
	$(PYTHON) tests/test_licence_headers.py

# Manual, needs Guix: evaluates the Scheme without building anything.
# Not part of `check` on purpose - a contributor without Guix must still pass.
check-guix-eval:
	$(GUIX) time-machine -C channels.lock.scm -- repl -L . tests/guix/source-module-evaluation.scm
	$(GUIX) time-machine -C channels.lock.scm -L . -- system -L . build systems/minimal.scm --dry-run
	$(GUIX) time-machine -C channels.lock.scm -L . -- system -L . build systems/desktop.scm --dry-run
	$(GUIX) time-machine -C channels.lock.scm -L . -- system -L . build systems/live.scm --dry-run
	$(GUIX) time-machine -C channels.lock.scm -L . -- system -L . build systems/live-minimal.scm --dry-run
	$(MAKE) check-compatibility-eval
	$(GUIX) time-machine -C channels.lock.scm -L . -- home -L . build systems/home.scm --dry-run

# Compatibility is opt-in and always uses its own authenticated Guix + Nonguix lock.
# This target resolves the lock and evaluates the full system graph without building it.
describe-compatibility-lock:
	$(GUIX) time-machine -C channels/compatibility.lock.scm -L . -- describe -f channels

check-compatibility-eval:
	$(PYTHON) scripts/check_channels.py --policy compatibility --lock channels/compatibility.lock.scm
	$(GUIX) time-machine -C channels/compatibility.lock.scm -L . -- describe -f channels
	$(GUIX) time-machine -C channels/compatibility.lock.scm -L . -- repl -L . tests/guix/compatibility-license-evaluation.scm
	$(GUIX) time-machine -C channels/compatibility.lock.scm -L . -- system -L . build systems/live-compat.scm --dry-run

# These two targets build local store outputs only; they do not install or write to physical disks.
build-compatibility-system:
	$(GUIX) time-machine -C channels/compatibility.lock.scm -L . -- system -L . build systems/live-compat.scm

image-live-compat:
	WSM_LIVE_PROFILE=systems/live-compat.scm WSM_CHANNEL_LOCK=channels/compatibility.lock.scm sh ./scripts/build_iso.sh

check-hygiene:
	$(PYTHON) tests/test_repo_hygiene.py

release-gate:
	$(PYTHON) scripts/release_gate.py --product "$(PRODUCT)" $(if $(ISO),--iso "$(ISO)") $(if $(BOOT),--boot)

check-branch-freshness:
	$(PYTHON) tests/test_branch_freshness.py

check-package-version:
	$(PYTHON) tests/test_package_version.py

check-fpc-manifest:
	$(PYTHON) tests/test_fpc_in_manifest.py

check-fpc-cli:
	$(PYTHON) tests/test_fpc_cli.py

check-fpc-preflight:
	$(PYTHON) tests/test_fpc_preflight.py

check-fpc-profile:
	$(PYTHON) tests/test_fpc_profile.py

check-fpc-partition:
	$(PYTHON) tests/test_fpc_partition.py

check-fpc-classify:
	$(PYTHON) tests/test_fpc_classify.py

# Build the six native FPC packages using the repository's pinned Guix channel.
build-fpc-packages:
	$(GUIX) time-machine -C channels.lock.scm -- build -L . wsm-hwcheck-fpc wsm-classify-fpc wsm-partition-fpc wsm-profile-fpc wsm-preflight-fpc wsm-install-fpc

check-fpc-package:
	$(PYTHON) tests/test_fpc_package.py

check-lean-closure:
	$(PYTHON) tests/test_lean_closure.py

check-guix-sign:
	$(PYTHON) tests/test_guix_sign.py

check-substitutes:
	$(PYTHON) tests/test_substitutes_workflow.py

check-narinfo:
	$(PYTHON) tests/test_narinfo_to_release_urls.py

check-cuirass:
	$(PYTHON) tests/test_cuirass_specs.py

check-channel-artifacts:
	$(PYTHON) scripts/check_channel_auth.py .
	$(PYTHON) tests/test_channel_auth.py

check-channels:
	$(PYTHON) tests/test_check_channels.py
	$(PYTHON) scripts/check_channels.py --policy free --lock channels.lock.scm
	@if test -f channels/compatibility.lock.scm; then \
		$(PYTHON) scripts/check_channels.py --policy compatibility --lock channels/compatibility.lock.scm; \
	else \
		printf '%s\\n' 'check-channels: Compatibility lock NOT_CONFIGURED; no Compatibility PASS'; \
	fi

check-profiles-matrix:
	$(PYTHON) tests/test_profiles.py

check-docs:
	$(PYTHON) tests/test_docs.py
	$(PYTHON) tests/test_upstreams_status.py

check-doc-ownership:
	$(PYTHON) tests/test_doc_ownership.py
	$(PYTHON) scripts/check_doc_ownership.py

check-regression-register:
	$(PYTHON) tests/test_omarchy_regression_register.py

check-release-info:
	$(PYTHON) tests/test_release_info_schema.py
	$(PYTHON) scripts/check_release_info.py

check-artifact-versions:
	$(PYTHON) tests/test_artifact_version_refusal.py

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
	$(PYTHON) tests/test_release_gate.py

describe-lock:
	$(GUIX) time-machine -C channels.lock.scm -- describe -f channels

check-locked-system:
	$(GUIX) time-machine -C channels.lock.scm -L . -- system -L . build systems/minimal.scm

# Компактний консольний live-носій із WSM CLI/TUI.
image-live-minimal:
	WSM_LIVE_PROFILE=systems/live-minimal.scm sh ./scripts/build_iso.sh

# Повні QEMU runtime checks запускаються лише вручну, не в `make check` і не в CI.
qemu-acceptance-manual:
	@for tool in qemu-system-x86_64 busybox cpio modprobe ldd gzip sudo mknod timeout zstd xz; do \
		command -v "$tool" >/dev/null || { echo "qemu-acceptance-manual: missing host tool: $tool" >&2; exit 1; }; \
	done
	command -v "$(QEMU_PYTHON)" >/dev/null
	"$(QEMU_PYTHON)" -c 'import sys, jsonschema; assert sys.version_info[:2] == (3, 11), sys.version'
	bash scripts/ci_qemu_guest_smoke.sh
	"$(QEMU_PYTHON)" scripts/ci_qemu_hwcheck_guest.py
	"$(QEMU_PYTHON)" scripts/ci_cxl_qemu_guest.py --timeout 90

release-bundle: check
	$(PYTHON) scripts/build_release_bundle.py

check-temp-paths:
	$(PYTHON) tests/test_temp_path_containment.py

check-test-registration:
	$(PYTHON) tests/test_test_registration.py

check-classification-policy:
	$(PYTHON) tests/test_classification_policy.py

check-readme-stage:
	$(PYTHON) tests/test_readme_stage.py

check-classification-schema:
	$(PYTHON) tests/test_classification_schema.py
	$(PYTHON) tests/test_artifact_version_refusal.py

check-ci-parity:
	$(PYTHON) tests/test_ci_parity.py

check-no-sleep-readiness:
	$(PYTHON) tests/test_system_definitions_have_no_sleep.py

check-ci-failure-visibility:
	$(PYTHON) tests/test_ci_failure_visibility.py

# Keep `make check` aligned with unittest discovery used by CI.
check-tests:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'

check-gp107-reference:
	$(PYTHON) tests/test_gp107_evidence_reference.py


check-release-docs:
	$(PYTHON) tests/test_release_documents_agree.py

check-channel-contract:
	$(PYTHON) tests/test_channel_contract.py

check-release-readiness:
	$(PYTHON) tests/test_release_readiness.py
