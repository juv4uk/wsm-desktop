#!/usr/bin/env bash
# Публікація WSM-пакетів під конкретне залізо (H170 + Kaby/Skylake).
#
# Цей скрипт запускає ВЛАСНИК на своїй машині. У середовищі, де його написали,
# немає ні Guix, ні guix-daemon, тому жодного прогону тут не було — і скрипт
# каже це прямо, замість того щоб вдавати перевірений.
#
# Навіщо окремий скрипт, а не команда в документі: публікація незворотна.
# Ключ, який підписує narinfo, — це повна довіра всьому, що він підписав, а
# бінарники, зібрані з --tune=native, падають на старіших CPU. Тому кожен крок
# тут або fail-closed, або явно названий.
#
# Використання:
#   scripts/publish-hardware-cache.sh --dry-run          # нічого не робить
#   scripts/publish-hardware-cache.sh --cpu skylake \
#       --license-decision custom-record                 # реальна публікація
#
# Прапорці рішення (без них скрипт відмовляє):
#   --license-decision custom-record   #367 вирішено: пакет несе власний license
#   --license-decision relicensed      #367 вирішено: код переліцензовано
#   --channel-unsigned-accepted        # канал свідомо публікується без підпису
#
# Межа: скрипт не вирішує #367 і не підписує канал. Він лише не дає зробити
# публікацію, не назвавши рішення вголос.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

die() { echo "PUBLISH-FAIL: $*" >&2; exit 2; }
note() { echo "publish: $*"; }

DRY_RUN=0
CPU=""
LICENSE_DECISION=""
UNSIGNED_ACCEPTED=0
CACHE_DIR="/var/cache/guix/publish"
ROOTS_DIR="/var/lib/wsm-publish-roots"
PORT=8080

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --cpu) shift; CPU="${1:-}" ;;
    --license-decision) shift; LICENSE_DECISION="${1:-}" ;;
    --channel-unsigned-accepted) UNSIGNED_ACCEPTED=1 ;;
    --cache) shift; CACHE_DIR="${1:-}" ;;
    --roots) shift; ROOTS_DIR="${1:-}" ;;
    --port) shift; PORT="${1:-}" ;;
    *) die "невідомий аргумент: $1" ;;
  esac
  shift
done

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
  if [ "$UNSIGNED_ACCEPTED" -ne 1 ]; then
    die "немає .guix-authorizations. Непідписаний канал можна збирати локально,
         але не можна публікувати як автентифікований. Якщо публікація без
         підпису — це свідоме рішення, передайте --channel-unsigned-accepted."
  fi
  note "канал публікується без підпису: це прийнято явно"
fi

# --- 3. CPU ------------------------------------------------------------------
# --tune=native заборонено: він запікає мікроархітектуру машини збірки, і такі
# бінарники падають з illegal instruction на старішому CPU. Публікуємо лише
# явно названу мікроархітектуру.
if [ -z "$CPU" ]; then
  die "не вказано --cpu. Для H170 з Kaby/Skylake-класом передайте явну назву
       (наприклад skylake), а не native."
fi
[ "$CPU" = "native" ] && die "--tune=native заборонено для публікації: бінарники
       можуть падати на іншому CPU. Назвіть мікроархітектуру явно."

# Skylake-покоління Pentium/Celeron не має AVX2, і -march=skylake на них падає.
# Перевіряємо прапорці CPU, а не назву моделі.
# -march=skylake вимагає не лише AVX2: ще BMI1/BMI2, FMA, MOVBE і XSAVE-сімейство.
# Перевірка лише avx2 пропустила б частину Skylake-покоління Pentium/Celeron.
if [ -r /proc/cpuinfo ]; then
  required_features="avx2 bmi1 bmi2 fma movbe xsave"
  missing_features=""
  for feature in $required_features; do
    grep -qw "$feature" /proc/cpuinfo || missing_features="$missing_features $feature"
  done
  if [ -n "$missing_features" ]; then
    die "CPU не має:$missing_features — -march=$CPU дасть illegal instruction.
         Публікуйте без --tune або з нижчою мікроархітектурою."
  fi
  note "прапорці CPU для $CPU присутні: $required_features"
else
  note "WARN: /proc/cpuinfo недоступний, прапорці CPU не перевірено"
fi

# --- 4. Що саме публікуємо ---------------------------------------------------
# Лише Free-профілі. Compatibility тягне nonfree, і політика #586 забороняє
# його розповсюдження без письмового clearance.
PACKAGES=(wsm-tools)
note "цілі: ${PACKAGES[*]} (лише Free; Compatibility не публікується — #586)"

if [ "$DRY_RUN" -eq 1 ]; then
  cat <<EOF
publish: DRY RUN — нічого не виконано. План:

  1. guix archive --generate-key            (якщо ключа ще немає)
  2. guix build --tune=$CPU --root=$ROOTS_DIR/<pkg> -L . ${PACKAGES[*]}
  3. guix publish --port=$PORT --cache=$CACHE_DIR --workers=2 --ttl=90d
  4. curl http://localhost:$PORT/nix-cache-info
  5. на споживачі:
       guix archive --authorize < /etc/guix/signing-key.pub
       guix build --substitute-urls=http://<host>:$PORT -C channels.lock.scm ...

  Межа: крок 2 доводить, що деривація збирається на цій машині. Він не доводить,
  що система завантажується і що H170 сертифіковано.
EOF
  exit 0
fi

command -v guix >/dev/null 2>&1 || die "guix не знайдено в PATH"

# --- 5. Ключ ----------------------------------------------------------------
if [ ! -f /etc/guix/signing-key.sec ]; then
  note "генерую ключ підпису кешу (потрібен root)"
  guix archive --generate-key || die "не вдалося згенерувати ключ"
else
  note "ключ підпису вже є: /etc/guix/signing-key.sec"
fi

# --- 6. Збірка з GC-коренями ------------------------------------------------
# Без --root guix gc видалить зібрані елементи, і опубліковані narinfo стануть
# 404. Це не теорія: саме так «кеш ламається сам».
install -d -m 0755 "$ROOTS_DIR" 2>/dev/null || true
for package in "${PACKAGES[@]}"; do
  note "збірка $package з --tune=$CPU (тести при tuned-збірці НЕ виконуються —
       це поведінка Guix, не наша; окремо проганяйте нетестований build для перевірки)"
  guix build -L . --tune="$CPU" --root="$ROOTS_DIR/$package" "$package" \
    || die "збірка $package не вдалася"
done

# --- 6b. Перевірка, що збірка справді tuned ---------------------------------
# guix build друкує рядок "tuning <pkg> for CPU <name>" лише для пакетів із
# властивістю tunable?; для решти --tune — тихий no-op. Тому перевіряємо
# прапорці у build-лозі, а не сподіваємось.
for package in "${PACKAGES[@]}"; do
  if log=$(guix build -L . --tune="$CPU" "$package" --log-file 2>/dev/null) && [ -f "$log" ]; then
    if grep -q -- "-march=$CPU" "$log"; then
      note "$package: -march=$CPU підтверджено в build-лозі"
    else
      note "WARN: $package зібрано без -march=$CPU — пакет не позначений tunable?, тюнінг не застосовано"
    fi
  else
    note "WARN: build-лог для $package недоступний, тюнінг не підтверджено"
  fi
done

# --- 7. Публікація ----------------------------------------------------------
install -d -m 0755 "$CACHE_DIR" 2>/dev/null || true
note "запускаю guix publish на порту $PORT"
note "споживач авторизує /etc/guix/signing-key.pub — це повна довіра всьому, що ключ підписав"
exec guix publish --port="$PORT" --cache="$CACHE_DIR" --workers=2 --ttl=90d
