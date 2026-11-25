# Профілі заліза

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Кожен зареєстрований профіль має теку `profiles/hardware/<vendor>/<model>/`:

```
profiles/hardware/asus/h170-pro/
  profile.scm
  evidence.json
  artifacts/
    dmesg.txt
```

**Профіль без валідного `evidence.json` не вважається підтвердженим профілем.** Це гіпотеза, і в інсталяторі вона не повинна брати участі.

## Вміст evidence bundle

Обов'язкові поля описані в [контракті evidence](../../docs/HARDWARE-PROFILE-EVIDENCE.md). Зокрема:

- `report_id` та `report_schema_version` — посилання на джерельний звіт `wsm-hwcheck`;
- `isa_level` — підтверджений рівень або `unknown`;
- `verified_functions`, `known_limitations` і непорожній `not_assessed`;
- непорожній `artifacts`, де кожен елемент має `kind`, `path` і `sha256`.

`path` — відносний шлях від теки профілю. Файл має існувати всередині `artifacts/` або іншого підкаталогу профілю; абсолютні шляхи, `..` та symlink-и заборонені. Валідатор читає файл і перевіряє SHA-256, а не лише формат digest.

`verified_by` приймає лише ролі `автори проєкту`, `local agent` або `web agent`. Особисті імена та адреси не зберігаються.

Шаблон — [`template.json`](template.json). Усі placeholder-и та нульовий SHA-256 треба замінити реальними значеннями; шаблон не є доказом і не повинен проходити валідацію без справжніх артефактів.

## Перевірка

```sh
make check-profile-evidence
python3 scripts/check_profile_evidence.py --dir /path/to/hardware-profiles
```

Скрипт:
- знаходить кожен `profile.scm` та вимагає поруч `evidence.json`;
- відхиляє evidence bundle без парного `profile.scm`;
- перевіряє schema, `slug`, неперсональну роль, статуси функцій та SHA-256 файлів;
- працює з нестандартним коренем, переданим у `--dir`.

Якщо профілів ще немає, команда повідомляє про порожній стан і завершується з кодом 0. Якщо знайдено профіль без evidence або будь-яку помилку перевірки — код 1. Неіснуючий шлях — код 2.

## Межі

Наявність валідного bundle не означає, що всі функції перевірені: `not_assessed` має залишатися непорожнім. QEMU, Windows і WSL результати не можуть підміняти native Linux перевірку фізичного обладнання. Формат не доводить, що інсталятор уже застосовує цей gate у runtime.
