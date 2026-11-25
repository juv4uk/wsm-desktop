# Профілі заліза

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Кожен повний профіль має теку `profiles/hardware/<vendor>/<model>/`:

```
profiles/hardware/vendor/model/
  profile.scm
  evidence.json
  artifacts/
    dmesg.txt
```

Обидва файли `profile.scm` та `evidence.json` обов'язкові. Перевірка дерева відхиляє неповну теку або evidence без відповідного профілю.

## Evidence v2

Контракт описаний у [документі доказів](../../docs/HARDWARE-PROFILE-EVIDENCE.md). Bundle містить:

- `report_id` і `report_schema_version` джерельного звіту `wsm-hwcheck`;
- `isa_level` із `wsm-cpu-isa/1` або `unknown`;
- `verified_functions`, `known_limitations` та непорожній `not_assessed`;
- непорожній список `artifacts` з `kind`, безпечним відносним `path` і SHA-256 фактичних байтів.

Артефакти зберігаються всередині теки профілю. Абсолютні шляхи, traversal-сегменти, symlink-и та mismatch hash заборонені. `verified_by` приймає лише неперсональні ролі: `автори проєкту`, `local agent`, `web agent`.

Шаблон — [`template.json`](template.json). Він містить placeholder-и й синтетичні значення; його не можна трактувати як реальний доказ або додавати до каталогу профілів без заміни всіх полів і справжніх артефактів.

## Перевірка

```sh
make check-profile-evidence
python3 scripts/check_profile_evidence.py --dir /path/to/hardware-profiles
```

Команда повного сканування:
- вимагає `profile.scm` та `evidence.json` у кожній теці `<vendor>/<model>`;
- перевіряє slug каталогу, schema, календарну дату, статуси й роль;
- звіряє SHA-256 із байтами файлів;
- відхиляє symlink, traversal і відсутні артефакти.

Порожній корінь без зареєстрованих model directories — нормальний стан, код 0. Виявлена неповна або невалідна тека — код 1; відсутній корінь — код 2.

## Межі

Жодного реального hardware profile наразі не заведено. Синтетичні тести підтверджують роботу валідатора, а не сумісність ASUS/Gigabyte H170, Intel/NVIDIA GPU або будь-якої іншої фізичної машини. WSL/QEMU результати не прирівнюються до bare-metal Linux evidence.
