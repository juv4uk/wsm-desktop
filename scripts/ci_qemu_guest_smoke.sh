#!/usr/bin/env bash
# SPDX-License-Identifier: LicenseRef-Volnist
# Real guest-kernel smoke test for GitHub Actions. This is not a WSM image test.
set -Eeuo pipefail

readonly MARKER="WSM_QEMU_GUEST_INIT_OK"
readonly TIMEOUT_SECONDS=45
readonly WORK_DIR="$(mktemp -d "${RUNNER_TEMP:-/tmp}/wsm-qemu-guest.XXXXXX")"
readonly ROOTFS="$WORK_DIR/rootfs"
readonly INITRD="$WORK_DIR/initramfs.cpio.gz"
readonly SERIAL_LOG="$WORK_DIR/serial.log"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

fail() {
  printf 'QEMU guest smoke: ERROR: %s\n' "$*" >&2
  if [[ -f "$SERIAL_LOG" ]]; then
    printf '%s\n' '--- serial output ---' >&2
    tail -n 100 "$SERIAL_LOG" >&2 || true
  fi
  exit 1
}

command -v qemu-system-x86_64 >/dev/null || fail "qemu-system-x86_64 is missing"
command -v busybox >/dev/null || fail "static BusyBox is missing"
command -v cpio >/dev/null || fail "cpio is missing"
command -v timeout >/dev/null || fail "timeout is missing"

mapfile -t KERNEL_IMAGES < <(find /boot -maxdepth 1 -type f -name "vmlinuz-*" -print | sort -V)
((${#KERNEL_IMAGES[@]} > 0)) || fail "no bootable Linux kernel image found under /boot"
KERNEL="${KERNEL_IMAGES[-1]}"
GUEST_KERNEL="$WORK_DIR/guest-kernel"
sudo cp "$KERNEL" "$GUEST_KERNEL"
sudo chmod 0644 "$GUEST_KERNEL"
printf "QEMU guest smoke: selected guest kernel %s\n" "$(basename "$KERNEL")"

mkdir -p "$ROOTFS/bin" "$ROOTFS/dev" "$ROOTFS/proc" "$ROOTFS/sys"
cp "$(command -v busybox)" "$ROOTFS/bin/busybox"
ln -s busybox "$ROOTFS/bin/sh"
sudo mknod -m 600 "$ROOTFS/dev/console" c 5 1
sudo mknod -m 666 "$ROOTFS/dev/ttyS0" c 4 64

cat > "$ROOTFS/init" <<'INIT'
#!/bin/sh
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev || true
echo "WSM_QEMU_GUEST_INIT_OK"
sync
poweroff -f
INIT
chmod 0755 "$ROOTFS/init"

(
  cd "$ROOTFS"
  find . -print0 | sort -z | cpio --null --create --format=newc
) | gzip -9 > "$INITRD"

[[ -s "$INITRD" ]] || fail "initramfs was not created"

printf 'QEMU guest smoke: booting runner kernel with TCG; no disk and no network.\n'
set +e
timeout --signal=TERM --kill-after=5s "$TIMEOUT_SECONDS" \
  qemu-system-x86_64 \
    -machine q35,accel=tcg \
    -cpu max \
    -m 512 \
    -smp 1 \
    -kernel "$GUEST_KERNEL" \
    -initrd "$INITRD" \
    -append "console=ttyS0,115200 rdinit=/init panic=-1" \
    -display none \
    -serial stdio \
    -monitor none \
    -nic none \
    -no-reboot \
    > "$SERIAL_LOG" 2>&1
QEMU_STATUS=$?
set -e

if ! grep -Fq "$MARKER" "$SERIAL_LOG"; then
  fail "guest init marker was not observed (QEMU exit=$QEMU_STATUS)"
fi

if [[ "$QEMU_STATUS" -ne 0 ]]; then
  fail "guest printed its marker but QEMU did not exit cleanly (exit=$QEMU_STATUS)"
fi

printf 'QEMU guest smoke: PASS — real guest kernel executed /init and printed %s.\n' "$MARKER"
