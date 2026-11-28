#!/usr/bin/env bash
# SPDX-License-Identifier: LicenseRef-Volnist
#
# Встановлення GNU Guix без залежності від Savannah cgit.
#
# Навіщо власний скрипт: офіційний `guix-install.sh` віддається через cgit
# Savannah, який відмовляє автоматичним клієнтам (wget: exit 8). Через це перші
# прогони збірки образу падали, не доходячи до Guix. Релізний тарбол на
# ftp.gnu.org віддається нормально і є документованим ручним встановленням.
#
# Це не форк інсталятора й не заміна офіційного. Це той самий набір кроків,
# записаний так, щоб його можна було виконати без інтерактивної сесії:
# розпакувати, створити групу й користувачів збірки, авторизувати ключ
# ci.guix.gnu.org, підняти guix-daemon.
#
# Використання:
#   ./scripts/install-guix.sh                  # версія за замовчуванням
#   GUIX_VERSION=1.5.0 ./scripts/install-guix.sh
#   GUIX_PREFIX=/opt/guix ./scripts/install-guix.sh
#
# Скрипт потребує root (sudo) для /gnu, /var/guix і системних користувачів.

set -euo pipefail

GUIX_VERSION="${GUIX_VERSION:-1.5.0}"
GUIX_PREFIX="${GUIX_PREFIX:-/usr/local}"
TARBALL="guix-binary-${GUIX_VERSION}.x86_64-linux.tar.xz"
URL="https://ftp.gnu.org/gnu/guix/${TARBALL}"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

fail() {
    printf 'install-guix: %s\n' "$1" >&2
    exit "${2:-1}"
}

command -v wget >/dev/null || fail "потрібен wget" 2
command -v xz >/dev/null || fail "потрібен xz" 2

printf 'install-guix: завантажую %s\n' "$URL"
wget -q -O "$WORKDIR/$TARBALL" "$URL" || fail "не вдалося завантажити $URL" 3

printf 'install-guix: розпаковую\n'
tar -xf "$WORKDIR/$TARBALL" -C "$WORKDIR" || fail "не вдалося розпакувати тарбол" 4

sudo mkdir -p /var/guix /gnu "$GUIX_PREFIX"
sudo mv "$WORKDIR/var/guix/"* /var/guix/ 2>/dev/null || true
sudo mv "$WORKDIR/gnu/"* /gnu/ 2>/dev/null || true

# Група й користувачі збірки: без них guix-daemon не має під ким збирати, і
# кожна збірка падає з повідомленням про невідому групу.
sudo groupadd --system guixbuild 2>/dev/null || true
for i in $(seq -w 1 10); do
    sudo useradd -g guixbuild -G guixbuild -d /var/empty \
        -s "$(command -v nologin || echo /usr/sbin/nologin)" \
        -c "Guix build user $i" --system "guixbuilder$i" 2>/dev/null || true
done

PROFILE_GUIX=/var/guix/profiles/per-user/root/current-guix
sudo ln -sf "$PROFILE_GUIX/bin/guix" "$GUIX_PREFIX/bin/guix"

# Ключ підпису замін: без нього guix не приймає жодного бінарника з ci.guix.gnu.org
# і починає збирати все з нуля — це години замість хвилин.
KEY="$PROFILE_GUIX/share/guix/ci.guix.gnu.org.pub"
if [ -s "$KEY" ]; then
    sudo "$GUIX_PREFIX/bin/guix" archive --authorize < "$KEY"
else
    printf 'install-guix: УВАГА, ключ %s не знайдено — заміни не прийматимуться\n' "$KEY" >&2
fi

# Демон. --disable-chroot, бо контейнери й раннери часто не дають mount namespace.
if ! pgrep -x guix-daemon >/dev/null 2>&1; then
    sudo "$PROFILE_GUIX/bin/guix-daemon" --build-users-group=guixbuild \
        --disable-chroot >/dev/null 2>&1 &
    for _ in $(seq 1 30); do
        pgrep -x guix-daemon >/dev/null 2>&1 && break
        sleep 1
    done
fi
pgrep -x guix-daemon >/dev/null 2>&1 || fail "guix-daemon не піднявся" 5

printf 'install-guix: версія — %s\n' "$("$GUIX_PREFIX/bin/guix" --version | head -n1)"
printf 'install-guix: готово. Додайте %s/bin до PATH.\n' "$GUIX_PREFIX"
