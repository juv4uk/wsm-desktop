# Модуль wsm-guix-deploy

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

Це місце для майбутнього Python job module Calamares. Файлу `module.desc` та Calamares entry point тут навмисно немає, тому frontend не може випадково завантажити незавершений installer backend.

## Поточна реалізація

Backend-незалежний адаптер розміщено в `wsm_install/backend_guix.py`; standalone CLI — у `wsm_install/guix_deploy.py`. Імпорт Calamares не потрібен.

Спочатку можна отримати точні digest-и для review:

```sh
python3 -m wsm_install.guix_deploy \
  --plan /path/to/confirmed-plan.json \
  --selection /path/to/target-selection.json \
  --show-confirmation
```

Після окремого підтвердження незмінного плану й вибору цілі CLI створює новий `.scm` файл у `/run/wsm/system.scm` і повертає структурований argv:

```sh
python3 -m wsm_install.guix_deploy \
  --plan /path/to/confirmed-plan.json \
  --selection /path/to/target-selection.json \
  --confirm-plan-sha256 <plan-sha256> \
  --confirm-target-digest <target-digest>
```

Шляхи не вибираються користувачем: backend дозволяє лише `/run/wsm/system.scm` і `/mnt`. CLI відхиляє path overrides, symlink-компоненти target mountpoint, output усередині target filesystem, перезапис наявного файлу, duplicate JSON keys, malformed або diagnostic-only plans, blockers і неправильні digest-и. Файл створюється атомарно з правами `0600`.

Поле `source_report.report_id` перевіряється на 16–80 ASCII символів `[A-Za-z0-9_-]`, а `source_report.sha256` — на рівно 64 lowercase hex. Перевірка виконується на backend boundary, бо ці значення потрапляють у Scheme-коментар; caller не може обійти її лише повторним обчисленням `plan_sha256`.

CLI повертає JSON із argv на кшталт `guix system init ...`, але **ніколи не запускає цю команду**, не монтує, не форматує та не змінює диск.

Поточний `wsm-install` CLI усе ще генерує `confirmable=false`; повноцінний frontend, який збирає всі обов'язкові selections і видає confirmed plan, ще не реалізовано. Тому handoff CLI наразі тестується на синтетичному confirmed fixture.

## Контракт майбутнього Calamares job module

Реальний модуль повинен використовувати Python job-module API саме тієї версії Calamares, яку WSM обере й зафіксує. До виклику backend він зобов'язаний перевірити одну однозначну ціль, EFI mount для UEFI, типи файлових систем, доступний обсяг, вибраний profile та ownership bootloader.

## Межі й перевірки

`tests/test_backend_guix.py` перевіряє provenance injection, installer-owned paths і allowlists; `tests/test_guix_deploy_cli.py` — двофазне підтвердження, приватний файл, output isolation, symlink/duplicate-key refusal. Тести не потребують Guix і не торкаються дисків.

Фактичний `guix system init`, mount/partition/filesystem operations, повторна перевірка identity цілі та QEMU installed-system boot залишаються окремими наступними кроками з власним execution contract, автентифікованим Guix channel snapshot і disposable disk image.