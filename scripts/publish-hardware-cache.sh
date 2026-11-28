#!/usr/bin/env bash
# Публікація WSM-пакетів під конкретне залізо (H170 + Kaby/Skylake).
#
# Цей скрипт запускає ВЛАСНИК на своїй машині. У середовищі, де його написали,
# немає ні Guix, ні guix-daemon, тому жодного прогону з Guix тут не було.
# Перевірено: синтаксис, відмови, dry-run. Не перевірено: реальна збірка.
#
# Навіщо окремий скрипт, а не команда в документі: публікація незворотна.
# Ключ, який підписує narinfo, — це повна довіра всьому, що він підписав, а
# бінарники з --tune=native падають на іншому CPU. Тому кожен крок тут або
# fail-closed, або явно названий.
#
# Використання:
#   scripts/publish-hardware-cache.sh --dry-run          # показати план
#   sudo scripts/publish-hardware-cache.sh --cpu skylake \
#       --license-decision custom-record --channel-unsigned-accepted
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

die() { echo "PUBLISH-FAIL: $*" >&2; exit 2; }
note() { echo "publish: $*"; }

DRY_RUN=0
CPU=""
LICENSE_DECISION=""
UNSIGNED_ACCEPTED=0
SKIP_CPU_CHECK=0
CACHE_DIR="/var/cache/guix/publish"
ROOTS_DIR="/var/lib/wsm-publish-roots"
PORT=8080
GUIX_SYSCONFDIR="${GUIX_SYSCONFDIR:-/etc/guix}"

# Кожен прапорець із значенням спершу перевіряє, що значення взагалі є:
# інакше `--cpu` останнім аргументом з'їдає сам себе і падає на shift без
# жодного діагностичного повідомлення.
need_value() {
  [ "$#" -ge 2 ] || die "$1 потребує значення"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --cpu) need_value "$@"; CPU="$2"; shift ;;
    --license-decision) need_value "$@"; LICENSE_DECISION="$2"; shift ;;
    --channel-unsigned-accepted) UNSIGNED_ACCEPTED=1 ;;
    --skip-cpu-check) SKIP_CPU_CHECK=1 ;;
    --cache) need_value "$@"; CACHE_DIR="$2"; shift ;;
    --roots) need_value "$@"; ROOTS_DIR="$2"; shift ;;
    --port) need_value "$@"; PORT="$2"; shift ;;
    *) die "невідомий аргумент: $1" ;;
  esac
  shift
done

# --- 0. Dry-run: показати план, навіть якщо рішення ще не названі ------------
# Інакше `--dry-run` без решти аргументів падав би на перевірках нижче, і план
# не можна було б подивитися, не знаючи вже всіх відповідей.
if [ "$DRY_RUN" -eq 1 ]; then
  printf '%s\n' \
    "publish: DRY RUN — нічого не виконано." \
    "  рішення #367:  ${LICENSE_DECISION:-<не названо — реальний запуск відмовить>}" \
    "  канал:         $([ "$UNSIGNED_ACCEPTED" -eq 1 ] && echo 'без підпису, прийнято явно' || echo '<не названо — реальний запуск відмовить>')" \
    "  CPU:           ${CPU:-<не названо — реальний запуск відмовить>}" \
    "" \
    "План:" \
    "  1. перевірка root і ключа в $GUIX_SYSCONFDIR" \
    "  2. перевірка прапорців CPU для -march=${CPU:-<cpu>}" \
    "  3. guix build -L . --tune=${CPU:-<cpu>} --root=$ROOTS_DIR/<pkg> wsm-tools" \
    "  4. порівняння деривацій з --tune і без: якщо однакові — тюнінг не застосовано" \
    "  5. guix publish --port=$PORT --cache=$CACHE_DIR --user=guix-publish" \
    "" \
    "На споживачі:" \
    "  scp <host>:$GUIX_SYSCONFDIR/signing-key.pub ./publisher.pub" \
    "  sudo guix archive --authorize < ./publisher.pub" \
    "  guix time-machine -C channels.lock.scm -- build wsm-tools --substitute-urls=http://<host>:$PORT" \
    "" \
    "Межа: крок 3 доводить, що деривація збирається на цій машині. Він не доводить," \
    "що система завантажується і що H170 сертифіковано."
  exit 0
fi

# --- 1. Рішення власника -----------------------------------------------------
case "$LICENSE_DECISION" in
  custom-record|relicensed) note "рішення #367: $LICENSE_DECISION" ;;
  "") die "#367 не вирішено: передайте --license-decision custom-record або relicensed.
         Політика забороняє публікувати пакет із метаданими, що суперечать ліцензії,
         і забороняє маскувати це заміною ідентифікатора." ;;
  *) die "невідоме рішення #367: $LICENSE_DECISION" ;;
esac

# --- 2. Канал ----------------------------------------------------------------
if [ ! -f .guix-authorizations ]; then
  [ "$UNSIGNED_ACCEPTED" -eq 1 ] || die "немає .guix-authorizations. Непідписаний
         канал можна збирати локально, але не можна публікувати як
         автентифікований. Якщо публікація без підпису — це свідоме рішення,
         передайте --channel-unsigned-accepted."
  note "канал публікується без підпису: це прийнято явно"
fi

# --- 3. CPU ------------------------------------------------------------------
[ -n "$CPU" ] || die "не вказано --cpu. Для H170 з Kaby/Skylake-класом
       передайте явну назву (наприклад skylake), а не native."
[ "$CPU" = "native" ] && die "--tune=native заборонено для публікації: бінарники
       можуть падати на іншому CPU. Назвіть мікроархітектуру явно."

# -march=skylake вимагає не лише AVX2. GCC перелічує для skylake: AVX, XSAVE,
# AVX2, BMI, BMI2, LZCNT, FMA, MOVBE, HLE, RDSEED, ADCX, PREFETCHW, AES,
# CLFLUSHOPT, XSAVEC, XSAVES, а також F16C і POPCNT. LZCNT ядро показує як 'abm'.
# Перевірка лише avx2 пропустила б частину Skylake-покоління Pentium/Celeron.
if [ "$SKIP_CPU_CHECK" -eq 1 ]; then
  note "перевірку прапорців CPU пропущено явно (--skip-cpu-check)"
elif [ -r /proc/cpuinfo ]; then
  required_features="avx avx2 f16c fma bmi1 bmi2 movbe xsave xsavec xsaves abm adx aes pclmulqdq popcnt fsgsbase rdseed"
  missing_features=""
  for feature in $required_features; do
    grep -qw "$feature" /proc/cpuinfo || missing_features="$missing_features $feature"
  done
  if [ -n "$missing_features" ]; then
    die "CPU не має:$missing_features — -march=$CPU дасть illegal instruction.
         Публікуйте без --tune або з нижчою мікроархітектурою."
  fi
  note "прапорці CPU для $CPU присутні"
else
  # Цей крок fail-closed: без /proc/cpuinfo ми не знаємо, чи бінарник взагалі
  # запуститься. Продовжувати з неперевіреною мікроархітектурою — саме те, від
  # чого скрипт мав захищати.
  die "не вдалося прочитати /proc/cpuinfo: прапорці CPU для --tune=$CPU не
       перевірено. Якщо перевірку зроблено вручну — передайте --skip-cpu-check."
fi

# --- 4. Root і ключ ----------------------------------------------------------
# guix archive --generate-key пише в системний sysconfdir, а guix publish читає
# звідти ключ підпису: обидва потребують root. Краще сказати це одразу, ніж
# отримати голу помилку доступу посеред збірки.
[ "$(id -u)" -eq 0 ] || die "запускайте від root: ключ підпису живе в
       $GUIX_SYSCONFDIR і доступний лише адміністратору."

if [ ! -f "$GUIX_SYSCONFDIR/signing-key.sec" ] || [ ! -f "$GUIX_SYSCONFDIR/signing-key.pub" ]; then
  note "генерую ключ підпису кешу в $GUIX_SYSCONFDIR"
  guix archive --generate-key || die "не вдалося згенерувати ключ"
else
  note "ключ підпису вже є: $GUIX_SYSCONFDIR/signing-key.sec"
fi

# --- 5. Що саме публікуємо ---------------------------------------------------
# Лише Free-профілі. Compatibility тягне nonfree, і політика #586 забороняє
# його розповсюдження без письмового clearance.
PACKAGES=(wsm-tools)
note "цілі: ${PACKAGES[*]} (лише Free; Compatibility не публікується — #586)"

command -v guix >/dev/null 2>&1 || die "guix не знайдено в PATH"

# Каталоги створюємо без `|| true`: інакше EACCES тут перетворюється на незрозумілу
# помилку пізніше, у guix build --root або в guix publish.
install -d -m 0755 "$ROOTS_DIR" || die "не вдалося створити $ROOTS_DIR"
install -d -m 0755 "$CACHE_DIR" || die "не вдалося створити $CACHE_DIR"

# --- 6. Збірка з GC-коренями ------------------------------------------------
# Без --root guix gc видалить зібрані елементи, і опубліковані narinfo стануть
# 404. Це не теорія: саме так «кеш ламається сам».
for package in "${PACKAGES[@]}"; do
  note "збірка $package з --tune=$CPU"
  note "  (tuned-збірка НЕ проганяє тести — це поведінка Guix, не наша)"
  guix build -L . --tune="$CPU" --root="$ROOTS_DIR/$package" "$package" \
    || die "збірка $package не вдалася"
done

# --- 6b. Чи справді застосовано тюнінг --------------------------------------
# Grep по build-лозі тут не працює двічі: логи стиснуті (.bz2), а -march
# вставляє компіляторний wrapper Guix, а не configure/make пакета — у лозі його
# немає. Тому порівнюємо деривації: якщо вони однакові, --tune нічого не змінив
# (пакет без властивості tunable? або збірку взято заміною).
for package in "${PACKAGES[@]}"; do
  plain=$(guix build -L . -d "$package") || die "не вдалося отримати деривацію $package"
  tuned=$(guix build -L . --tune="$CPU" -d "$package") || die "не вдалося отримати деривацію $package з --tune"
  if [ "$plain" = "$tuned" ]; then
    note "WARN: --tune=$CPU не змінив $package (немає властивості tunable?) — публікується нетюнінгований бінарник"
  else
    note "$package: деривація з --tune відрізняється від звичайної — тюнінг застосовано"
  fi
done

# --- 7. Публікація ----------------------------------------------------------
note "запускаю guix publish на порту $PORT"
note "споживач авторизує ПУБЛІЧНИЙ ключ ЦІЄЇ машини ($GUIX_SYSCONFDIR/signing-key.pub),"
note "  скопійований до себе: це повна довіра всьому, що ключ підписав"
exec guix publish --user=guix-publish --port="$PORT" --cache="$CACHE_DIR" \
  --workers=2 --ttl=90d
