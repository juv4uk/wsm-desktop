#!/usr/bin/env bash
# SPDX-License-Identifier: LicenseRef-Volnist
#
# CI/ephemeral-runner bootstrap for the official GNU Guix binary distribution.
# This is NOT a fork/replacement for the official foreign-distribution
# installer and does not configure a persistent init-system service.
#
# The binary tarball is verified against the official release OpenPGP
# signature BEFORE extraction or any privileged filesystem operation.
# For Guix 1.5.0, the release-signing primary key is Efraim Flashner's
# A28BF40C3E551372662D14F741AAE7DCCA3D8351 (published by GNU Guix).
#
# Usage:
#   ./scripts/install-guix.sh
#   GUIX_VERSION=1.5.0 GUIX_PREFIX=/opt/guix ./scripts/install-guix.sh
#
# Running without chroot isolation is disabled by default. Only use
# GUIX_ALLOW_UNSANDBOXED_BUILDS=1 on a disposable CI runner when the runner
# cannot provide Guix's normal build chroot. Never use that override for a
# multi-user or production host.

set -euo pipefail
umask 077

GUIX_VERSION="${GUIX_VERSION:-1.5.0}"
GUIX_PREFIX="${GUIX_PREFIX:-/usr/local}"
SIGNING_KEY_URL="https://codeberg.org/efraim.gpg"
SIGNING_KEY_FINGERPRINT="A28BF40C3E551372662D14F741AAE7DCCA3D8351"
TARBALL="guix-binary-${GUIX_VERSION}.x86_64-linux.tar.xz"
URL="https://ftp.gnu.org/gnu/guix/${TARBALL}"
WORKDIR="$(mktemp -d)"
GNUPGHOME="${WORKDIR}/gnupg"
trap 'rm -rf -- "$WORKDIR"' EXIT

fail() {
    printf 'install-guix: ERROR: %s\n' "$1" >&2
    exit "${2:-1}"
}

as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

[ "$(uname -s)" = "Linux" ] || fail "підтримується лише Linux" 2
[ "$(uname -m)" = "x86_64" ] || fail "ця збірка tarball призначена лише для x86_64" 2
[[ "$GUIX_VERSION" =~ ^[0-9]+([.][0-9]+)+$ ]] || fail "невалідна GUIX_VERSION" 2
[[ "$GUIX_PREFIX" = /* ]] || fail "GUIX_PREFIX має бути абсолютним шляхом" 2

for tool in wget gpg tar xz getent pgrep; do
    command -v "$tool" >/dev/null 2>&1 || fail "потрібна команда: $tool" 2
done
if [ "$(id -u)" -ne 0 ]; then
    command -v sudo >/dev/null 2>&1 || fail "потрібен sudo або запуск від root" 2
    sudo -v || fail "sudo authorization failed" 2
fi

# Refuse to overlay an existing Guix installation.
if [ -e /gnu ] || [ -e /var/guix ]; then
    fail "знайдено /gnu або /var/guix; відмовляюся перезаписувати наявну інсталяцію"
fi

mkdir -m 0700 "$GNUPGHOME"

printf 'install-guix: завантажую binary tarball та detached signature\n'
wget -q -O "$WORKDIR/$TARBALL" "$URL" || fail "не вдалося завантажити $URL" 3
wget -q -O "$WORKDIR/$TARBALL.sig" "$URL.sig" || fail "не вдалося завантажити detached signature" 3
test -s "$WORKDIR/$TARBALL" || fail "binary tarball порожній" 3
test -s "$WORKDIR/$TARBALL.sig" || fail "detached signature порожній" 3

printf 'install-guix: імпортую release key та звіряю fingerprint\n'
wget -q -O "$WORKDIR/efraim.gpg" "$SIGNING_KEY_URL" || fail "не вдалося завантажити офіційний release key" 3
test -s "$WORKDIR/efraim.gpg" || fail "release key порожній" 3
gpg --homedir "$GNUPGHOME" --batch --quiet --import "$WORKDIR/efraim.gpg" \
    || fail "не вдалося імпортувати release key" 4

mapfile -t IMPORTED_FINGERPRINTS < <(
    gpg --homedir "$GNUPGHOME" --batch --with-colons --fingerprint --list-keys 2>/dev/null \
        | awk -F: '$1 == "fpr" { print toupper($10); exit }'
)
[ "${#IMPORTED_FINGERPRINTS[@]}" -eq 1 ] \
    || fail "не вдалося однозначно прочитати primary fingerprint" 4
[ "${IMPORTED_FINGERPRINTS[0]}" = "$SIGNING_KEY_FINGERPRINT" ] \
    || fail "неочікуваний release key fingerprint: ${IMPORTED_FINGERPRINTS[0]}" 4

printf 'install-guix: перевіряю OpenPGP signature перед extract\n'
if ! gpg --homedir "$GNUPGHOME" --batch --no-tty --status-fd 1 \
        --verify "$WORKDIR/$TARBALL.sig" "$WORKDIR/$TARBALL" \
        >"$WORKDIR/gpg-status.txt" 2>"$WORKDIR/gpg.log"; then
    cat "$WORKDIR/gpg.log" >&2
    fail "OpenPGP signature verification failed" 4
fi
if ! awk -v expected="$SIGNING_KEY_FINGERPRINT" '
    $1 == "[GNUPG:]" && $2 == "VALIDSIG" && ($3 == expected || $NF == expected) {
        valid = 1
    }
    END { exit !valid }
' "$WORKDIR/gpg-status.txt"; then
    fail "signature valid, але її signer не відповідає pinned Guix release key" 4
fi

printf 'install-guix: розпаковую перевірений tarball у приватний каталог\n'
tar --warning=no-timestamp -xf "$WORKDIR/$TARBALL" -C "$WORKDIR" \
    || fail "не вдалося розпакувати перевірений tarball" 5
test -d "$WORKDIR/var/guix" || fail "tarball не містить var/guix" 5
test -d "$WORKDIR/gnu/store" || fail "tarball не містить gnu/store" 5
test -e "$WORKDIR/var/guix/profiles/per-user/root/current-guix" \
    || test -L "$WORKDIR/var/guix/profiles/per-user/root/current-guix" \
    || fail "tarball не містить root current-guix profile" 5

printf 'install-guix: встановлюю перевірені файли\n'
as_root mv -- "$WORKDIR/var/guix" /var/guix
as_root mv -- "$WORKDIR/gnu" /gnu

PROFILE_GUIX=/var/guix/profiles/per-user/root/current-guix
as_root test -x "$PROFILE_GUIX/bin/guix" || fail "Guix executable відсутній після встановлення" 6
as_root test -x "$PROFILE_GUIX/bin/guix-daemon" || fail "guix-daemon відсутній після встановлення" 6

NOLOGIN="$(command -v nologin || command -v false || true)"
[ -n "$NOLOGIN" ] && [ -x "$NOLOGIN" ] || fail "не знайдено nologin executable" 6

if ! getent group guixbuild >/dev/null 2>&1; then
    as_root groupadd --system guixbuild
fi
for i in $(seq -w 1 10); do
    user="guixbuilder$i"
    if getent passwd "$user" >/dev/null 2>&1; then
        [ "$(id -gn "$user")" = "guixbuild" ] \
            || fail "$user існує, але його primary group не guixbuild"
    else
        as_root useradd --system --gid guixbuild --groups guixbuild \
            --home-dir /var/empty --shell "$NOLOGIN" \
            --comment "Guix build user $i" "$user"
    fi
done

as_root mkdir -p "$GUIX_PREFIX/bin" /root/.config/guix
as_root ln -sfn "$PROFILE_GUIX" /root/.config/guix/current
as_root ln -sfn "$PROFILE_GUIX/bin/guix" "$GUIX_PREFIX/bin/guix"
as_root ln -sfn "$PROFILE_GUIX/bin/guix-daemon" "$GUIX_PREFIX/bin/guix-daemon"

SUBSTITUTE_KEY="$PROFILE_GUIX/share/guix/ci.guix.gnu.org.pub"
as_root test -s "$SUBSTITUTE_KEY" || fail "відсутній ci.guix.gnu.org.pub у перевіреному profile"
as_root "$PROFILE_GUIX/bin/guix" archive --authorize < "$SUBSTITUTE_KEY"

if pgrep -x guix-daemon >/dev/null 2>&1; then
    fail "guix-daemon уже працює; не підключаюсь до невідомого daemon"
fi

DAEMON_ARGS=(--build-users-group=guixbuild)
if [ "${GUIX_ALLOW_UNSANDBOXED_BUILDS:-0}" = "1" ]; then
    printf 'install-guix: WARNING: запускаю daemon без chroot isolation на disposable runner\n' >&2
    DAEMON_ARGS+=(--disable-chroot)
fi

if [ "$(id -u)" -eq 0 ]; then
    nohup "$PROFILE_GUIX/bin/guix-daemon" "${DAEMON_ARGS[@]}" \
        >"$WORKDIR/guix-daemon.log" 2>&1 </dev/null &
else
    sudo -b "$PROFILE_GUIX/bin/guix-daemon" "${DAEMON_ARGS[@]}"
fi

for _ in $(seq 1 30); do
    pgrep -x guix-daemon >/dev/null 2>&1 && break
    sleep 1
done
pgrep -x guix-daemon >/dev/null 2>&1 || {
    cat "$WORKDIR/guix-daemon.log" >&2 2>/dev/null || true
    fail "guix-daemon не запустився" 7
}

printf 'install-guix: встановлено %s\n' "$("$PROFILE_GUIX/bin/guix" --version | head -n1)"
printf 'install-guix: binary tarball signature перевірена; daemon запущено\n'
printf 'install-guix: PATH helper: export PATH="%s/bin:$PATH"\n' "$GUIX_PREFIX"
printf 'install-guix: це ephemeral bootstrap, не persistent system service\n'
