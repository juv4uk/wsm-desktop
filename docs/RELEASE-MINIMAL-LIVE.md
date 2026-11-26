# WSM Desktop 0.1.0-rc3 — Minimal Live Installer Preview

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Це компактний live-носій на основі `systems/live-minimal.scm`: без KDE/Qt,
із мережею, апаратним preflight та власним WSM CLI/TUI. Він призначений для
завантаження WSM на слабкому обладнанні, збору локального звіту про пристрої
та відкриття майстра планування інсталяції.

## Запуск

1. Запишіть ISO на USB або відкрийте його у віртуальній машині.
2. Перейдіть на консоль `tty2` (`Ctrl+Alt+F2`): там налаштовано автоматичний
   вхід користувача `wsm`. `tty1` і serial console лишаються для boot logs.
3. Основна мова консолі — українська. `Alt+Shift` перемикає розкладки US/UA;
   перед введенням шляху `/dev/...` перемкніться на US. Вихід `q` і
   навігація `j/k` працюють і на українській розкладці (`й`, `о/л`).
4. Запустіть `wsm-install-live`.

Команда створює апаратний звіт у приватному тимчасовому каталозі, запускає
WSM TUI та після завершення видаляє тимчасові дані. Також доступні
`wsm-hwcheck --help` і `wsm-install --help`.

## Межі

- У цьому RC доступні hardware preflight і перегляд плану; APPLY вимкнено
  в усіх entrypoints. Носій не розбиває диск, не форматує розділи, не монтує
  цільову систему та не запускає `guix system init`.
- Free ISO використовує автентифікований офіційний Guix lock; Nonguix і
  proprietary firmware не додаються.
- Це QEMU boot acceptance у BIOS і UEFI, а не підтвердження сумісності
  кожної фізичної конфігурації.
- Release workflow не публікує ISO розміром 2 GiB або більше.

## Відтворюваність

Збірка виконується на GitHub-hosted Ubuntu runner з
`systems/live-minimal.scm` і `channels.lock.scm`. У релізі є ISO,
build/release manifests, SHA-256 і результати BIOS/UEFI boot smoke.
