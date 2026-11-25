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
LOCK="$ROOT/channels.lock.scm"

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
if len(matches) != 1:
    raise SystemExit("expected exactly one 40-character channel commit in channels.lock.scm")
print(matches[0])
PY
)

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR=$(CDPATH= cd -- "$OUTPUT_DIR" && pwd)
ISO_OUTPUT="$OUTPUT_DIR/wsm-desktop-live.iso"
ISO_ROOT="$OUTPUT_DIR/.wsm-desktop-live.iso-root"
BUILD_LOG="$OUTPUT_DIR/build.log"
CHANNELS_FILE="$OUTPUT_DIR/channels.resolved.scm"
CHANNELS_LOG="$OUTPUT_DIR/channel-resolution.log"
MANIFEST_FILE="$OUTPUT_DIR/manifest.json"
CHECKSUMS_FILE="$OUTPUT_DIR/SHA256SUMS"

# Preserve every previous attempt; use a fresh WSM_ISO_DIR for another run.
for output in "$ISO_OUTPUT" "$ISO_ROOT" "$BUILD_LOG" "$CHANNELS_FILE" "$CHANNELS_LOG" "$MANIFEST_FILE" "$CHECKSUMS_FILE"; do
    if [ -e "$output" ] || [ -L "$output" ]; then
        printf '%s\n' "build-iso: refusing to overwrite existing output: $output" >&2
        exit 3
    fi
done

# Read the version from the pinned channel, not only from the bootstrap
# Guix executable. The -L option makes the repository's WSM modules visible
# inside this exact time-machine invocation.
GUIX_LOCKED_VERSION=$(guix time-machine -C "$LOCK" -L "$ROOT" -- --version | sed -n '1p')
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
printf '%s\n' "build-iso: GC root=$ISO_ROOT"
printf '%s\n' "build-iso: resolving locked channels (Guix authentication is not disabled)"

# Resolve the exact channel set through the same time-machine lock used below.
if guix time-machine -C "$LOCK" -L "$ROOT" -- describe -f channels >"$CHANNELS_FILE" 2>"$CHANNELS_LOG"; then
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
if guix time-machine -C "$LOCK" -L "$ROOT" -- system image \
    --no-grafts \
    --root="$ISO_ROOT" \
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

if [ ! -L "$ISO_ROOT" ] || [ ! -e "$ISO_ROOT" ]; then
    printf '%s\n' "build-iso: Guix returned success but did not create the expected GC-root link." >&2
    exit 4
fi
STORE_PATH=$(readlink -f "$ISO_ROOT")
if [ ! -f "$STORE_PATH" ] || [ ! -s "$STORE_PATH" ]; then
    printf '%s\n' "build-iso: resolved image is missing, not a regular file, or empty." >&2
    exit 4
fi

# The GC-root remains a symlink to the immutable store object. The user-facing
# ISO must be a regular file so QEMU and release uploaders do not need to
# dereference a store link outside the output directory.
ISO_TEMP=$(mktemp "$OUTPUT_DIR/.wsm-desktop-live.iso.tmp.XXXXXX")
cleanup_iso_temp() {
    if [ -n "$ISO_TEMP" ]; then
        rm -f -- "$ISO_TEMP"
    fi
}
trap cleanup_iso_temp EXIT HUP INT TERM
if ! cp -- "$STORE_PATH" "$ISO_TEMP"; then
    printf '%s\n' "build-iso: cannot materialize the ISO from the Guix store." >&2
    exit 4
fi
if ! python3 - "$ISO_TEMP" "$ISO_OUTPUT" "$STORE_PATH" <<'PY'
import hashlib
import os
import sys
from pathlib import Path

temporary = Path(sys.argv[1])
destination = Path(sys.argv[2])
store_image = Path(sys.argv[3])

def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

try:
    if destination.exists() or destination.is_symlink():
        raise SystemExit(f"refusing to overwrite existing ISO: {destination}")
    if not temporary.is_file() or temporary.stat().st_size == 0:
        raise SystemExit("materialized ISO is missing, not regular, or empty")
    if not store_image.is_file() or temporary.stat().st_size != store_image.stat().st_size:
        raise SystemExit("materialized ISO size differs from the Guix store image")
    if digest(temporary) != digest(store_image):
        raise SystemExit("materialized ISO checksum differs from the Guix store image")
    os.chmod(temporary, 0o644)
    with temporary.open("rb") as stream:
        os.fsync(stream.fileno())
    # link() atomically creates the destination and refuses to overwrite it.
    os.link(temporary, destination)
    temporary.unlink()
except Exception:
    try:
        temporary.unlink()
    except OSError:
        pass
    raise
PY
then
    printf '%s\n' "build-iso: failed to publish a regular ISO file." >&2
    exit 4
fi
ISO_TEMP=""
trap - EXIT HUP INT TERM
if [ ! -f "$ISO_OUTPUT" ] || [ -L "$ISO_OUTPUT" ] || [ ! -s "$ISO_OUTPUT" ]; then
    printf '%s\n' "build-iso: materialized ISO is not a non-empty regular file." >&2
    exit 4
fi

WSM_SOURCE_COMMIT="$SOURCE_COMMIT" \
WSM_CHANNEL_COMMIT="$CHANNEL_COMMIT" \
WSM_CHANNEL_TRUST_WARNING="$CHANNEL_TRUST_WARNING" \
WSM_GUIX_LOCKED_VERSION="$GUIX_LOCKED_VERSION" \
WSM_PROFILE="$PROFILE" \
WSM_PROFILE_SHA256="$PROFILE_SHA256" \
WSM_LOCK="$LOCK" \
WSM_ISO_OUTPUT="$ISO_OUTPUT" \
WSM_GC_ROOT="$ISO_ROOT" \
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
gc_root = Path(os.environ["WSM_GC_ROOT"])
store_path = Path(os.environ["WSM_STORE_PATH"])
channels = Path(os.environ["WSM_CHANNELS_FILE"])
channels_log = Path(os.environ["WSM_CHANNELS_LOG"])
build_log = Path(os.environ["WSM_BUILD_LOG"])
profile = Path(os.environ["WSM_PROFILE"])
lock = Path(os.environ["WSM_LOCK"])
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
        "gc_root": gc_root.name,
        "size_bytes": iso.stat().st_size,
        "sha256": digest(iso),
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
            "guix", "time-machine", "-C", str(lock), "-L", str(lock.parent), "--",
            "system", "image", "--no-grafts", f"--root={gc_root}", "--image-type=iso9660",
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
