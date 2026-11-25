#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Збирає завантажувальний ISO WSM Desktop із systems/live.scm.
#
# Скрипт навмисно відмовляється працювати без Guix: мовчазний вихід із
# кодом 0 без образу — гірший за зрозумілу помилку.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PROFILE="${WSM_LIVE_PROFILE:-$ROOT/systems/live.scm}"
OUTPUT_DIR="${WSM_ISO_DIR:-$ROOT/build}"

if ! command -v guix >/dev/null 2>&1; then
    printf '%s\n' "build-iso: guix not found in PATH." >&2
    printf '%s\n' "  Цей скрипт не може зібрати образ без Guix і не вдає, що може." >&2
    printf '%s\n' "  Встановіть Guix і повторіть: https://guix.gnu.org/manual/en/html_node/Installation.html" >&2
    exit 127
fi

if [ ! -f "$PROFILE" ]; then
    printf '%s\n' "build-iso: profile not found: $PROFILE" >&2
    exit 2
fi

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR=$(CDPATH= cd -- "$OUTPUT_DIR" && pwd)
ISO_OUTPUT="$OUTPUT_DIR/wsm-desktop-live.iso"

# Never replace an earlier image or follow an existing symlink.
if [ -e "$ISO_OUTPUT" ] || [ -L "$ISO_OUTPUT" ]; then
    printf '%s\n' "build-iso: refusing to overwrite existing output: $ISO_OUTPUT" >&2
    exit 3
fi

printf '%s\n' "build-iso: profile $PROFILE"
printf '%s\n' "build-iso: output  $ISO_OUTPUT"
printf '%s\n' "build-iso: this takes a long time on a cold store" >&2

# --no-grafts прибирає варіативність, яку вносить графік трансплантацій:
# без нього два прогони можуть дати різні результати для того самого коміту.
# --root створює посилання на точний результат у OUTPUT_DIR; без нього
# Guix виводить store path, а оголошений каталог лишається порожнім.
guix system image \
    --no-grafts \
    --root="$ISO_OUTPUT" \
    --image-type=iso9660 \
    --system=x86_64-linux \
    "$PROFILE"

if [ ! -L "$ISO_OUTPUT" ] || [ ! -e "$ISO_OUTPUT" ]; then
    printf '%s\n' "build-iso: Guix returned success but did not create the expected image link." >&2
    exit 4
fi

printf '%s\n' "build-iso: image $ISO_OUTPUT"
printf '%s\n' "build-iso: done" >&2
