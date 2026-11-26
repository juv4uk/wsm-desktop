#!/bin/sh
# SPDX-License-Identifier: LicenseRef-Volnist
#
# Створює WSM live ISO лише з каналу, зафіксованого в channels.lock.scm.
# Скрипт не позначає образ перевіреним до окремого QEMU/OVMF boot test.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

PROFILE="${WSM_LIVE_PROFILE:-$ROOT/systems/live.scm}"
OUTPUT_DIR="${WSM_ISO_DIR:-$ROOT/build}"
# Two products, two locks. The Compatibility image needs Nonguix, and building it
# from the free lock is not a small mistake: the profile imports (nongnu ...)
# modules that the free channel set cannot resolve, so the build would fail
# late, after Guix has already been fetched.
LOCK="${WSM_CHANNEL_LOCK:-$ROOT/channels.lock.scm}"
case "$LOCK" in
    /*) ;;
    *) LOCK="$ROOT/$LOCK" ;;
esac

case "$PROFILE" in
    /*) ;;
    *) PROFILE="$ROOT/$PROFILE" ;;
esac

if ! command -v guix >/dev/null 2>&1; then
    printf '%s\n' "build-iso: guix not found in PATH." >&2
    exit 127
fi
for tool in git python3 readlink grep; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf '%s\n' "build-iso: required tool not found: $tool" >&2
        exit 127
    fi
done
for required in "$LOCK" "$PROFILE"; do
    if [ ! -f "$required" ]; then
        printf '%s\n' "build-iso: required file not found: $required" >&2
        exit 2
    fi
done

# Provenance must refer to an exact, committed source tree, not an edited
# worktree or a local recipe that differs from the recorded source commit.
if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
    printf '%s\n' "build-iso: refusing to build from a dirty worktree." >&2
    git status --short >&2
    exit 5
fi
SOURCE_COMMIT=$(git rev-parse HEAD)

# The project channel lock currently contains one Guix channel. Fail closed
# if the lock shape changes instead of silently recording an empty revision.
CHANNEL_COMMIT=$(python3 - "$LOCK" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
matches = re.findall(r'\(commit\s+"([0-9a-f]{40})"\)', text)
names = re.findall(r"\(name\s+'(\S+)\)", text)
if not matches:
    raise SystemExit(f"no 40-character channel commit in {sys.argv[1]}")
if "nonguix" in names and len(matches) < 2:
    raise SystemExit("the lock names nonguix but pins fewer than two commits")
# The first commit is always Guix: the profile language and the store come from it.
print(matches[0])
print(",".join(names), file=sys.stderr)
PY
)

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR=$(CDPATH= cd -- "$OUTPUT_DIR" && pwd)
ISO_OUTPUT="$OUTPUT_DIR/wsm-desktop-live.iso"
BUILD_LOG="$OUTPUT_DIR/build.log"
CHANNELS_FILE="$OUTPUT_DIR/channels.resolved.scm"
CHANNELS_LOG="$OUTPUT_DIR/channel-resolution.log"
MANIFEST_FILE="$OUTPUT_DIR/manifest.json"
CHECKSUMS_FILE="$OUTPUT_DIR/SHA256SUMS"

# Preserve every previous attempt; use a fresh WSM_ISO_DIR for another run.
for output in "$ISO_OUTPUT" "$BUILD_LOG" "$CHANNELS_FILE" "$CHANNELS_LOG" "$MANIFEST_FILE" "$CHECKSUMS_FILE"; do
    if [ -e "$output" ] || [ -L "$output" ]; then
        printf '%s\n' "build-iso: refusing to overwrite existing output: $output" >&2
        exit 3
    fi
done

# Pass -L to the inferior Guix itself, not to the outer time-machine command.
# Everything after "--" is argv for the locked Guix instance.
GUIX_LOCKED_VERSION=$(guix time-machine -C "$LOCK" -- -L "$ROOT" --version | sed -n '1p')
PROFILE_SHA256=$(python3 - "$PROFILE" <<'PY'
import hashlib
import sys
from pathlib import Path
digest = hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()
print(digest)
PY
)

printf '%s\n' "build-iso: source=$SOURCE_COMMIT"
printf '%s\n' "build-iso: channel=$CHANNEL_COMMIT"
printf '%s\n' "build-iso: profile=$PROFILE"
printf '%s\n' "build-iso: output=$ISO_OUTPUT"
printf '%s\n' "build-iso: resolving locked channels (Guix authentication is not disabled)"

# Resolve the exact channel set through the same time-machine lock used below.
if guix time-machine -C "$LOCK" -- -L "$ROOT" describe -f channels >"$CHANNELS_FILE" 2>"$CHANNELS_LOG"; then
    :
else
    status=$?
    printf '%s\n' "build-iso: locked channel resolution failed (exit $status)" >&2
    tail -n 80 "$CHANNELS_LOG" >&2 || true
    exit "$status"
fi
if [ ! -s "$CHANNELS_FILE" ]; then
    printf '%s\n' "build-iso: locked channel description is empty." >&2
    exit 6
fi
if grep -Eiq 'channel authentication disabled' "$CHANNELS_FILE" "$CHANNELS_LOG"; then
    printf '%s\n' "build-iso: refusing to build because channel authentication is disabled." >&2
    grep -Ein 'channel authentication disabled' "$CHANNELS_FILE" "$CHANNELS_LOG" >&2 || true
    exit 7
fi

printf '%s\n' "build-iso: building with locked Guix channel; see build.log"
if guix time-machine -C "$LOCK" -- -L "$ROOT" system image \
    --no-grafts \
    --root="$ISO_OUTPUT" \
    --image-type=iso9660 \
    --system=x86_64-linux \
    "$PROFILE" >"$BUILD_LOG" 2>&1; then
    :
else
    status=$?
    printf '%s\n' "build-iso: image build failed (exit $status)" >&2
    tail -n 100 "$BUILD_LOG" >&2 || true
    exit "$status"
fi

# A successful command that explicitly reports disabled channel authentication
# is not acceptable evidence for this pinned build.
if grep -Eiq 'channel authentication disabled' "$CHANNELS_FILE" "$CHANNELS_LOG" "$BUILD_LOG"; then
    printf '%s\n' "build-iso: refusing an image resolved with channel authentication disabled." >&2
    grep -Ein 'channel authentication disabled' "$CHANNELS_FILE" "$CHANNELS_LOG" "$BUILD_LOG" >&2 || true
    exit 7
fi
CHANNEL_TRUST_WARNING=false
if grep -Eiq 'channel is not trusted|channel .* not trusted' "$CHANNELS_FILE" "$CHANNELS_LOG" "$BUILD_LOG"; then
    CHANNEL_TRUST_WARNING=true
fi

if [ ! -L "$ISO_OUTPUT" ] || [ ! -e "$ISO_OUTPUT" ]; then
    printf '%s\n' "build-iso: Guix returned success but did not create the expected image link." >&2
    exit 4
fi
STORE_PATH=$(readlink -f "$ISO_OUTPUT")
if [ ! -f "$STORE_PATH" ] || [ ! -s "$STORE_PATH" ]; then
    printf '%s\n' "build-iso: resolved image is missing, not a regular file, or empty." >&2
    exit 4
fi

WSM_SOURCE_COMMIT="$SOURCE_COMMIT" \
WSM_CHANNEL_COMMIT="$CHANNEL_COMMIT" \
WSM_CHANNEL_TRUST_WARNING="$CHANNEL_TRUST_WARNING" \
WSM_GUIX_LOCKED_VERSION="$GUIX_LOCKED_VERSION" \
WSM_PROFILE="$PROFILE" \
WSM_PROFILE_SHA256="$PROFILE_SHA256" \
WSM_LOCK="$LOCK" \
WSM_REPO_ROOT="$ROOT" \
WSM_ISO_OUTPUT="$ISO_OUTPUT" \
WSM_STORE_PATH="$STORE_PATH" \
WSM_CHANNELS_FILE="$CHANNELS_FILE" \
WSM_CHANNELS_LOG="$CHANNELS_LOG" \
WSM_BUILD_LOG="$BUILD_LOG" \
WSM_MANIFEST_FILE="$MANIFEST_FILE" \
WSM_CHECKSUMS_FILE="$CHECKSUMS_FILE" \
python3 - <<'PY'
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

iso = Path(os.environ["WSM_ISO_OUTPUT"])
store_path = Path(os.environ["WSM_STORE_PATH"])
channels = Path(os.environ["WSM_CHANNELS_FILE"])
channels_log = Path(os.environ["WSM_CHANNELS_LOG"])
build_log = Path(os.environ["WSM_BUILD_LOG"])
profile = Path(os.environ["WSM_PROFILE"])
lock = Path(os.environ["WSM_LOCK"])
repo_root = Path(os.environ["WSM_REPO_ROOT"])
manifest_path = Path(os.environ["WSM_MANIFEST_FILE"])
checksums_path = Path(os.environ["WSM_CHECKSUMS_FILE"])

manifest = {
    "schema_version": 1,
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "artifact": {
        "filename": iso.name,
        "format": "iso9660",
        "system": "x86_64-linux",
        "store_path": str(store_path),
        "size_bytes": store_path.stat().st_size,
        "sha256": digest(store_path),
    },
    "source": {
        "commit": os.environ["WSM_SOURCE_COMMIT"],
        "worktree_clean": True,
        "profile": str(profile),
        "profile_sha256": os.environ["WSM_PROFILE_SHA256"],
        "channel_lock": lock.name,
        "channel_lock_sha256": digest(lock),
        "locked_guix_channel_commit": os.environ["WSM_CHANNEL_COMMIT"],
        "untrusted_channel_warning_present": os.environ["WSM_CHANNEL_TRUST_WARNING"] == "true",
    },
    "guix": {
        "locked_version": os.environ["WSM_GUIX_LOCKED_VERSION"],
        "resolved_channels_file": channels.name,
        "resolved_channels_sha256": digest(channels),
        "channel_resolution_log": channels_log.name,
        "channel_resolution_log_sha256": digest(channels_log),
        "authentication_policy": (
            "Guix time-machine default; --disable-authentication is not passed. "
            "Inspect channel-resolution.log for trust warnings."
        ),
    },
    "build": {
        "command": [
            "guix", "time-machine", "-C", str(lock), "--", "-L", str(repo_root), "system", "image",
            "--no-grafts", f"--root={iso}", "--image-type=iso9660",
            "--system=x86_64-linux", str(profile),
        ],
        "log": build_log.name,
        "log_sha256": digest(build_log),
    },
}

manifest_path.write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

entries = [iso, manifest_path, channels, channels_log, build_log]
checksums_path.write_text(
    "".join(f"{digest(path)}  {path.name}\n" for path in entries),
    encoding="utf-8",
)
PY

printf '%s\n' "build-iso: image $ISO_OUTPUT"
printf '%s\n' "build-iso: manifest $MANIFEST_FILE"
printf '%s\n' "build-iso: checksums $CHECKSUMS_FILE"
printf '%s\n' "build-iso: QEMU/OVMF Plasma boot has NOT been verified by this command."
