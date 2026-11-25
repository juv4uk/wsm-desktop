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

printf '%s\n' "build-iso: profile $PROFILE"
printf '%s\n' "build-iso: output  $OUTPUT_DIR"
printf '%s\n' "build-iso: this takes a long time on a cold store" >&2

# --no-grafts прибирає варіативність, яку вносить графік трансплантацій:
# без нього два прогони можуть дати різні результати для того самого коміту.
guix system image \
    --no-grafts \
    --image-type=iso9660 \
    --system=x86_64-linux \
    "$PROFILE"

printf '%s\n' "build-iso: done" >&2
