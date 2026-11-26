#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Reassemble a WSM live ISO from GitHub release parts.
set -eu

if [ "$#" -ne 3 ]; then
    echo "usage: $0 <part-prefix> <output.iso> <SHA256SUMS>" >&2
    exit 2
fi

prefix=$1
output=$2
sums=$3

: > "$output"
n=1
while :; do
    part=$(printf '%s.part%03d' "$prefix" "$n")
    [ -f "$part" ] || break
    cat "$part" >> "$output"
    n=$((n + 1))
done

if [ "$n" -eq 1 ]; then
    echo "no parts found for prefix: $prefix" >&2
    exit 1
fi

printf '%s  %s\n' "$(sha256sum "$output" | cut -d' ' -f1)" "$(basename "$output")" \
    | grep -F -x -f - "$sums" >/dev/null
echo "reassembled $output from $((n - 1)) parts; SHA-256 verified"
