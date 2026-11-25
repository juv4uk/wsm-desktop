#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -Eeuo pipefail

PYTHON_ASSET="cpython-3.11.18+20261123-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261123/cpython-3.11.18%2B20261123-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PYTHON_SHA256="75b92c55bc6a5f58fe4d08fc5261c983b2b17930192d62946fe7c9cf6fd66316"
ROOT_DIR="$(cd "$(dirname "$BASH_SOURCE")/.." && pwd)"
WORK_DIR="$(mktemp -d "$RUNNER_TEMP/wsm-hwcheck-guest.XXXXXX")"
ARCHIVE="$WORK_DIR/$PYTHON_ASSET"
RUNTIME_DIR="$WORK_DIR/runtime"
ROOTFS="$WORK_DIR/rootfs"
INITRAMFS="$WORK_DIR/initramfs.cpio.gz"
GUEST_KERNEL="$WORK_DIR/guest-kernel"
DEPS_FILE="$WORK_DIR/dependencies.txt"

cleanup() { rm -rf "$WORK_DIR"; }
trap cleanup EXIT
fail() { printf 'wsm-hwcheck QEMU guest: ERROR: %s\n' "$*" >&2; exit 1; }

for tool in curl sha256sum tar readelf ldd cpio gzip qemu-system-x86_64 busybox; do
  command -v "$tool" >/dev/null 2>&1 || fail "required tool is missing: $tool"
done

printf 'Fetching pinned CPython 3.11.18 standalone asset...\n'
curl --fail --location --retry 3 --retry-delay 2 "$PYTHON_URL" --output "$ARCHIVE"
printf '%s  %s\n' "$PYTHON_SHA256" "$ARCHIVE" | sha256sum --check --status || fail "CPython runtime SHA-256 mismatch"

mkdir -p "$RUNTIME_DIR" "$ROOTFS/opt/python" "$ROOTFS/opt/wsm"
tar -xzf "$ARCHIVE" -C "$RUNTIME_DIR"
PYTHON_EXE="$(find -L "$RUNTIME_DIR" -type f -path '*/bin/python3.11' -print -quit)"
[[ -n "$PYTHON_EXE" && -x "$PYTHON_EXE" ]] || fail "pinned CPython executable was not found"
PYTHON_ROOT="$(dirname "$(dirname "$PYTHON_EXE")")"
[[ -d "$PYTHON_ROOT/lib/python3.11" ]] || fail "CPython standard library is missing"
printf 'Pinned runtime: %s\n' "$("$PYTHON_EXE" --version 2>&1)"
readelf -l "$PYTHON_EXE" | grep -F 'Requesting program interpreter' || fail "ELF interpreter was not found"

# The GNU install-only archive is dynamic. Discover the ELF dependency closure.
: > "$DEPS_FILE"
ELF_COUNT=0
while IFS= read -r -d '' ELF_FILE; do
  if ! readelf -h "$ELF_FILE" >/dev/null 2>&1; then continue; fi
  ELF_COUNT=$((ELF_COUNT + 1))
  LDD_OUTPUT="$(ldd "$ELF_FILE" 2>&1 || true)"
  if grep -q 'not found' <<<"$LDD_OUTPUT"; then
    printf 'Unresolved dependency in %s:\n%s\n' "$ELF_FILE" "$LDD_OUTPUT" >&2
    fail "CPython runtime has an unresolved ELF dependency"
  fi
  awk '$2 == "=>" && $3 ~ /^\// { print $3 } $1 ~ /^\// { print $1 }' <<<"$LDD_OUTPUT" >> "$DEPS_FILE"
done < <(find -L "$PYTHON_ROOT" -type f -print0)

(( ELF_COUNT > 0 )) || fail "no ELF files found in CPython runtime"
cp -a "$PYTHON_ROOT/." "$ROOTFS/opt/python/"
sort -u "$DEPS_FILE" -o "$DEPS_FILE"
while IFS= read -r LIBRARY; do
  [[ -e "$LIBRARY" ]] || fail "runtime dependency disappeared: $LIBRARY"
  REAL_LIBRARY="$(readlink -f "$LIBRARY")"
  case "$REAL_LIBRARY" in "$PYTHON_ROOT"/*) continue ;; esac
  install -D -m 0755 "$LIBRARY" "$ROOTFS$LIBRARY"
done < "$DEPS_FILE"
printf 'CPython ELF files inspected: %s\n' "$ELF_COUNT"

cp -a "$ROOT_DIR/wsm_hwcheck" "$ROOTFS/opt/wsm/"
cp "$(command -v busybox)" "$ROOTFS/bin/busybox"
for APPLET in sh cat mount mkdir poweroff dmesg; do ln -sfn busybox "$ROOTFS/bin/$APPLET"; done

mkdir -p "$ROOTFS/dev" "$ROOTFS/proc" "$ROOTFS/sys" "$ROOTFS/tmp"
sudo mknod -m 600 "$ROOTFS/dev/console" c 5 1
sudo mknod -m 600 "$ROOTFS/dev/ttyS0" c 4 64
sudo mknod -m 666 "$ROOTFS/dev/null" c 1 3

cat > "$ROOTFS/init" <<'INIT'
#!/bin/sh
PATH=/bin:/opt/python/bin
PYTHONHOME=/opt/python
PYTHONPATH=/opt/wsm
PYTHONNOUSERSITE=1
PYTHONDONTWRITEBYTECODE=1
LD_LIBRARY_PATH=/opt/python/lib:/lib:/lib64:/usr/lib:/usr/lib64:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu
export PATH PYTHONHOME PYTHONPATH PYTHONNOUSERSITE PYTHONDONTWRITEBYTECODE LD_LIBRARY_PATH

fail_guest() {
    printf 'WSM_HWCHECK_GUEST_ERROR: %s\n' "$1" > /dev/console
    /bin/poweroff -f
    while :; do /bin/busybox sleep 1; done
}

/opt/python/bin/python3.11 -S -B -c 'import datetime, fnmatch, hashlib, json, pathlib, platform, re, secrets, selectors, subprocess, time' >/tmp/python-runtime-smoke.txt 2>&1 || fail_guest "python runtime import smoke failed"
mount -t proc -o ro proc /proc || fail_guest "could not mount read-only procfs"
mount -t sysfs -o ro sysfs /sys || fail_guest "could not mount read-only sysfs"
mount -t devtmpfs devtmpfs /dev || true

/opt/python/bin/python3.11 -S -B -m wsm_hwcheck --compact --output /tmp/hardware-report.json >/tmp/wsm-hwcheck.stdout 2>/tmp/wsm-hwcheck.stderr
STATUS=$?
if [ "$STATUS" -ne 0 ] || [ ! -s /tmp/hardware-report.json ]; then
    /bin/cat /tmp/wsm-hwcheck.stdout /tmp/wsm-hwcheck.stderr > /dev/console
    fail_guest "wsm-hwcheck did not produce a report (exit=$STATUS)"
fi

printf 'WSM_HWCHECK_REPORT_BEGIN\n' > /dev/console
/bin/cat /tmp/hardware-report.json > /dev/console
printf '\nWSM_HWCHECK_REPORT_END\n' > /dev/console
printf 'WSM_HWCHECK_GUEST_DONE\n' > /dev/console
sync
/bin/poweroff -f
while :; do /bin/busybox sleep 1; done
INIT
chmod 0755 "$ROOTFS/init"

(
  cd "$ROOTFS"
  find . -print0 | sort -z | cpio --null --create --format=newc
) | gzip -9 > "$INITRAMFS"
[[ -s "$INITRAMFS" ]] || fail "initramfs was not created"

KERNEL="$(find /boot -maxdepth 1 -type f -name 'vmlinuz-*' -print | sort -V | tail -n 1)"
[[ -n "$KERNEL" ]] || fail "no runner kernel image found under /boot"
sudo cp "$KERNEL" "$GUEST_KERNEL"
sudo chmod 0644 "$GUEST_KERNEL"
printf 'Prepared guest kernel %s and initramfs (%s bytes).\n' "$(basename "$KERNEL")" "$(stat -c '%s' "$INITRAMFS")"

python -m scripts.ci_run_hwcheck_guest --kernel "$GUEST_KERNEL" --initramfs "$INITRAMFS" --schema "$ROOT_DIR/schemas/hardware-report.schema.json" --timeout-seconds 120
