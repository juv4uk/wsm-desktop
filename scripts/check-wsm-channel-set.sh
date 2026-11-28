#!/usr/bin/env bash
# SPDX-License-Identifier: LicenseRef-Volnist
# Diagnostic-only proof that Guix reads channels/wsm.scm and rejects its
# unauthenticated WSM entry when authentication is left enabled.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "\${BASH_SOURCE[0]}")/.." && pwd)"
GUIX_BIN="\${GUIX:-guix}"
CHANNELS="$ROOT/channels/wsm.scm"

fail() {
  printf 'wsm-channel-smoke: %s\n' "$1" >&2
  exit 1
}

command -v "$GUIX_BIN" >/dev/null 2>&1 || fail "Guix executable not found: $GUIX_BIN"
test -s "$CHANNELS" || fail "missing channel set: $CHANNELS"

WORK="$(mktemp -d)"
trap 'rm -rf -- "$WORK"' EXIT
export HOME="$WORK/home"
export XDG_CACHE_HOME="$HOME/.cache"
mkdir -p "$HOME" "$XDG_CACHE_HOME"

AUTH_LOG="$WORK/authentication.log"
if "$GUIX_BIN" time-machine -C "$CHANNELS" -- describe -f channels >"$AUTH_LOG" 2>&1; then
  cat "$AUTH_LOG" >&2
  fail "unauthenticated WSM channel unexpectedly passed with authentication enabled"
fi

# Do not accept a network, parse, or generic command failure as the expected
# result. The failure must identify the WSM channel's trust/introduction path.
if ! grep -Eiq '(wsm|juv4uk/wsm-desktop)' "$AUTH_LOG"; then
  cat "$AUTH_LOG" >&2
  fail "default refusal did not identify the WSM channel"
fi
if ! grep -Eiq '(authenticat|introduction|authoriz|signature|untrusted)' "$AUTH_LOG"; then
  cat "$AUTH_LOG" >&2
  fail "default refusal was not an authentication/introduction diagnostic"
fi
printf '%s\n' "WSM_CHANNEL_DEFAULT_AUTH=REFUSED_AS_EXPECTED"

DIAGNOSTIC_LOG="$WORK/diagnostic-only.log"
if ! "$GUIX_BIN" time-machine -C "$CHANNELS" --disable-authentication -- describe -f channels >"$DIAGNOSTIC_LOG" 2>&1; then
  cat "$DIAGNOSTIC_LOG" >&2
  fail "diagnostic-only channel read failed"
fi
if ! grep -Fq "(name 'guix)" "$DIAGNOSTIC_LOG"; then
  cat "$DIAGNOSTIC_LOG" >&2
  fail "Guix channel was not present in the evaluated channel set"
fi
if ! grep -Fq "(name 'wsm)" "$DIAGNOSTIC_LOG"; then
  cat "$DIAGNOSTIC_LOG" >&2
  fail "WSM channel was not present in the evaluated channel set"
fi

printf '%s\n' "WSM_CHANNELS_RESOLVED=guix,wsm"
printf '%s\n' "WSM_CHANNEL_AUTHENTICATION=NOT_TESTED"
printf '%s\n' "wsm-channel-smoke: diagnostic-only read; no release lock or production install used"
