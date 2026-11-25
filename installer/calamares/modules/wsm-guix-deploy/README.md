# Модуль wsm-guix-deploy

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

Це місце для майбутнього Python job module Calamares. Файлу \`module.desc\` та Calamares entry point тут навмисно немає, тому frontend не може випадково завантажити незавершений installer backend.

## Поточна реалізація

Backend-незалежний від frontend адаптер розміщено в \`wsm_install/backend_guix.py\`; standalone CLI — у \`wsm_install/guix_deploy.py\`. Імпорт Calamares не потрібен.

Спочатку можна отримати точні digest-и для review:

\`\`\`sh
python3 -m wsm_install.guix_deploy \\
  --plan /path/to/confirmed-plan.json \\
  --selection /path/to/target-selection.json \\
  --show-confirmation
\`\`\`

Після окремого підтвердження незмінного плану й вибору цілі CLI створює новий \`.scm\` файл і повертає структурований argv:

\`\`\`sh
python3 -m wsm_install.guix_deploy \\
  --plan /path/to/confirmed-plan.json \\
  --selection /path/to/target-selection.json \\
  --output /run/wsm/system.scm \\
  --confirm-plan-sha256 <plan-sha256> \\
  --confirm-target-digest <target-digest>
\`\`\`

CLI:
- відмовляє diagnostic-only або зміненим планам, blockers, неузгодженим digest-ам і невалідному вибору;
- створює новий файл із правами \`0600\`, не перезаписує наявний і не приймає symlink або duplicate JSON keys;
- повертає argv на кшталт \`guix system init ...\`, але **ніколи не запускає цю команду**;
- не монтує, не форматує та не змінює цільовий диск.

Поточний \`wsm-install\` CLI все ще генерує \`confirmable=false\`; повноцінний frontend, який збирає всі обов'язкові selections і видає confirmed plan, ще не реалізовано. Тому handoff CLI наразі тестується на синтетичному confirmed fixture.

## Контракт майбутнього Calamares job module

Реальний модуль повинен використовувати Python job-module API саме тієї версії Calamares, яку WSM обере й зафіксує. До виклику backend він зобов'язаний перевірити:
- одну однозначну ціль;
- очікуваний EFI mount для UEFI;
- типи файлових систем та ідентифікатори;
- стан mount і доступний обсяг;
- вибраний Free або Compatibility profile;
- згенеровану декларацію operating-system;
- ціль bootloader і точну команду.

## Правила безпечного виконання

- Використовувати документований Calamares command API; не використовувати \`os.system\` або \`shell=True\`.
- Не вставляти рядки з UI у shell command.
- Не вгадувати диск за позицією в списку.
- Не виконувати запис до підсумку й явного підтвердження.
- Не логувати паролі, password hashes, tokens або приватні дані.
- Не запускати одночасно Calamares bootloader job і Guix bootloader installation.
- За будь-якої невиконаної передумови зупинятися до \`guix system init\`.

## Перевірки та межі

\`tests/test_backend_guix.py\` перевіряє adapter refusal paths, \`tests/test_guix_deploy_cli.py\` — standalone CLI, підтвердження digest-ів і безпечне створення файлу. Тести не потребують Guix і не змінюють диски.

Фактичне виконання \`guix system init\`, mount/partition/filesystem operations, повторна перевірка identity цілі та QEMU installed-system boot залишаються наступними окремими кроками. Для них потрібні окремий execution contract, автентифікований Guix channel snapshot і disposable disk image.