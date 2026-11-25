#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build a disposable synthetic ISO and boot it through the real WSM QEMU harness.
set -Eeuo pipefail

readonly MARKER="WSM_QEMU_HARNESS_ISO_BOOT_OK"
readonly WORK_DIR="$(mktemp -d "${RUNNER_TEMP:-/tmp}/wsm-qemu-harness-iso.XXXXXX")"
readonly ISO_ROOT="$WORK_DIR/iso-root"
readonly ROOTFS="$WORK_DIR/rootfs"
readonly ISO_PATH="$WORK_DIR/wsm-qemu-harness.iso"
readonly RESULT="$WORK_DIR/harness-result.json"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

fail() {
  printf 'QEMU harness ISO integration: ERROR: %s\n' "$*" >&2
  if [[ -f "$RESULT" ]]; then
    printf '%s\n' '--- harness result ---' >&2
    cat "$RESULT" >&2 || true
  fi
  exit 1
}

for tool in qemu-system-x86_64 qemu-img grub-mkrescue xorriso cpio gzip busybox; do
  command -v "$tool" >/dev/null || fail "required tool is missing: $tool"
done

KERNEL_IMAGE="/boot/vmlinuz-$(uname -r)"
if [[ ! -f "$KERNEL_IMAGE" ]] || ! sudo test -r "$KERNEL_IMAGE"; then
  printf 'Runner kernel image is unavailable: %s\n' "$KERNEL_IMAGE" >&2
  ls -la /boot >&2 || true
  fail "no readable runner kernel image"
fi

mkdir -p "$ISO_ROOT/boot/grub" "$ROOTFS/bin" "$ROOTFS/dev"
# Copy the runner kernel as a read-only input; QEMU itself runs unprivileged.
sudo cat "$KERNEL_IMAGE" > "$ISO_ROOT/boot/vmlinuz"
chmod 0644 "$ISO_ROOT/boot/vmlinuz"

cp "$(command -v busybox)" "$ROOTFS/bin/busybox"
ln -s busybox "$ROOTFS/bin/sh"
sudo mknod -m 600 "$ROOTFS/dev/console" c 5 1

cat > "$ROOTFS/init" <<'INIT'
#!/bin/sh
echo WSM_QEMU_HARNESS_ISO_BOOT_OK > /dev/console
/bin/busybox poweroff -f
INIT
chmod 0755 "$ROOTFS/init"

(
  cd "$ROOTFS"
  find . -print0 | sort -z | cpio --null --create --format=newc
) | gzip -9 > "$ISO_ROOT/boot/initramfs.cpio.gz"

cat > "$ISO_ROOT/boot/grub/grub.cfg" <<'GRUB'
set timeout=0
set default=0
serial --unit=0 --speed=115200 --word=8 --parity=no --stop=1
terminal_input serial
terminal_output serial

menuentry "WSM QEMU harness integration guest" {
    linux /boot/vmlinuz console=ttyS0,115200 rdinit=/init panic=-1 loglevel=3
    initrd /boot/initramfs.cpio.gz
}
GRUB

grub-mkrescue --output="$ISO_PATH" "$ISO_ROOT" >/dev/null
[[ -s "$ISO_PATH" ]] || fail "synthetic ISO was not created"

printf 'Synthetic ISO created inside runner temp workspace.\n'
printf 'Running project QEMU harness with a disposable 256 MiB qcow2.\n'

set +e
python scripts/qemu_boot_smoke.py \
  --iso "$ISO_PATH" \
  --timeout-seconds 45 \
  --memory-mib 512 \
  --cpus 1 \
  --disk-size 256M \
  --boot-marker "$MARKER" \
  > "$RESULT"
HARNESS_STATUS=$?
set -e

cat "$RESULT"
[[ "$HARNESS_STATUS" -eq 0 ]] || fail "project harness returned status $HARNESS_STATUS"

python - "$RESULT" "$MARKER" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
marker = sys.argv[2]
assert payload["mode"] == "qemu-boot-smoke", payload
assert payload["boot_confirmed"] is True, payload
assert payload["boot_marker_configured"] is True, payload
assert marker in payload["serial_output_tail"], payload
assert payload["host_device_passthrough"] is False, payload
assert payload["network_enabled"] is False, payload
assert payload["efi_variable_store"] is False, payload
assert payload["guest_installer_execution"] is False, payload
print("PASS: the project QEMU harness booted the synthetic ISO and observed the guest marker.")
print("Scope: generic harness integration only; not a WSM installer or physical hardware test.")
PY
