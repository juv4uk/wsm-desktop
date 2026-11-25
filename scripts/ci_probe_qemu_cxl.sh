#!/usr/bin/env bash
set -euo pipefail

SUMMARY_FILE="${GITHUB_STEP_SUMMARY:-/dev/null}"
report() {
  printf '%s\n' "$*" | tee -a "$SUMMARY_FILE"
}

KERNEL_RELEASE="$(uname -r)"
QEMU_BIN="$(command -v qemu-system-x86_64 || true)"

report "# CXL QEMU capability probe"
report ""
report "- Runner: ${ImageVersion:-unknown} / ${ImageOS:-unknown}"
report "- Kernel release: `$KERNEL_RELEASE`"
report "- Probe mode: host-side QEMU model construction only"
report "- No kernel modules are loaded; no guest is booted."

CONFIG_FILE="/boot/config-$KERNEL_RELEASE"
CONFIG_TEXT=""
if [[ -r "$CONFIG_FILE" ]]; then
  CONFIG_TEXT="$(grep -E '^(CONFIG_CXL_(BUS|PCI|ACPI|MEM|PORT|REGION|PMEM)=|# CONFIG_CXL_(BUS|PCI|ACPI|MEM|PORT|REGION|PMEM) is not set)' "$CONFIG_FILE" || true)"
elif [[ -r /proc/config.gz ]] && command -v zcat >/dev/null 2>&1; then
  CONFIG_TEXT="$(zcat /proc/config.gz | grep -E '^(CONFIG_CXL_(BUS|PCI|ACPI|MEM|PORT|REGION|PMEM)=|# CONFIG_CXL_(BUS|PCI|ACPI|MEM|PORT|REGION|PMEM) is not set)' || true)"
fi

report ""
report "## Kernel CXL configuration"
if [[ -n "$CONFIG_TEXT" ]]; then
  report '```text'
  report "$CONFIG_TEXT"
  report '```'
else
  report "Kernel config unavailable or exposes no matching CXL symbols; classify as unknown."
fi

report ""
report "## Kernel module availability (inspection only)"
if command -v modinfo >/dev/null 2>&1; then
  for module in cxl_core cxl_pci cxl_acpi cxl_mem cxl_port; do
    module_file="$(modinfo -F filename "$module" 2>/dev/null || true)"
    vermagic="$(modinfo -F vermagic "$module" 2>/dev/null || true)"
    if [[ -n "$module_file" ]]; then
      report "- $module: $module_file; vermagic=${vermagic:-unknown}"
    else
      report "- $module: no loadable module found (could be built-in or unavailable)"
    fi
  done
else
  report "modinfo is unavailable; module state is unknown."
fi

report ""
report "## QEMU version and CXL device models"
if [[ -z "$QEMU_BIN" ]]; then
  report "qemu-system-x86_64 is unavailable."
  report "QEMU CXL topology parse: unavailable"
  exit 0
fi

QEMU_VERSION="$("$QEMU_BIN" --version | head -n 1)"
report "- QEMU: $QEMU_VERSION"
DEVICE_HELP="$("$QEMU_BIN" -device help 2>&1 || true)"
MODELS_OK=1
for model in pxb-cxl cxl-rp cxl-type3; do
  if grep -Fq "$model" <<<"$DEVICE_HELP"; then
    report "- device model $model: present"
  else
    report "- device model $model: unavailable"
    MODELS_OK=0
  fi
done

if [[ "$MODELS_OK" -ne 1 ]]; then
  report ""
  report "**QEMU CXL topology parse: unavailable** (one or more device models are missing)."
  report "This is a runner capability result, not a hardware incompatibility verdict."
  exit 0
fi

QEMU_LOG="$(mktemp)"
trap 'rm -f "$QEMU_LOG"' EXIT

# Start the QEMU machine paused. The timeout is expected: this probe validates
# that the emulator accepts the CXL topology; it does not boot a guest kernel.
set +e
timeout --signal=TERM --kill-after=1s 4s "$QEMU_BIN" \
  -nodefaults \
  -no-user-config \
  -machine q35,cxl=on \
  -m 1G,maxmem=8G,slots=8 \
  -smp 1 \
  -object memory-backend-ram,id=vmem0,share=on,size=256M \
  -device pxb-cxl,bus_nr=12,bus=pcie.0,id=cxl.1 \
  -device cxl-rp,port=0,bus=cxl.1,id=root_port13,chassis=0,slot=2 \
  -device cxl-type3,bus=root_port13,volatile-memdev=vmem0,id=cxl-vmem0 \
  -machine cxl-fmw.0.targets.0=cxl.1,cxl-fmw.0.size=4G \
  -display none \
  -serial none \
  -monitor none \
  -nic none \
  -S >"$QEMU_LOG" 2>&1
QEMU_RC=$?
set -e

report ""
if [[ "$QEMU_RC" -eq 124 ]]; then
  report "**QEMU CXL topology parse: accepted** (QEMU remained alive until the expected timeout)."
elif [[ "$QEMU_RC" -eq 137 ]]; then
  report "**QEMU CXL topology parse: inconclusive** (QEMU required SIGKILL after the timeout)."
else
  report "**QEMU CXL topology parse: rejected** (exit code $QEMU_RC)."
fi

report ""
report "### Bounded QEMU diagnostic"
report '```text'
tail -n 30 "$QEMU_LOG" || true
report '```'

report ""
report "## Interpretation"
report "- This probe does not boot a guest and does not prove Linux CXL driver discovery."
report "- Host kernel config/module metadata is only a candidate for a later guest initramfs; no module was loaded."
report "- No disk, NIC, host-device passthrough, CXL region creation, decoder programming, or physical hardware was used."
report "- Missing configuration or models mean environment unavailable/unknown, not unsupported hardware."
