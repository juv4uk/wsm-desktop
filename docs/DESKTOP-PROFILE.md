# Десктопний профіль і live-образ

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **не зібрано й не перевірено**
- Критичний шлях: **так** — без цього немає ні образу, ні десктопа
- Дата: 2026-11-25

## Що тут є

| Файл | Що описує |
| --- | --- |
| `systems/desktop.scm` | цільова система: KDE Plasma, SDDM, NetworkManager, звук, шрифти з кирилицею, українська локаль |
| `systems/live.scm` | live-профіль для завантажувального ISO: те саме плюс пакет `wsm-tools` |
| `wsm/packages/wsm.scm` | пакетне визначення наших інструментів для Guix |
| `scripts/build_iso.sh` | збірка ISO з `systems/live.scm` |
| `tests/test_system_profiles.py` | структурні перевірки профілів без Guix |

## Чого тут немає — і чому

**Це не перевірено.** У середовищі, де ці файли написані, немає ні Guix, ні QEMU, і `guix.gnu.org` недоступний. Жоден рядок нижче не виконано. За принципом 8 проєкту («безпечна відмова») це позначено в заголовку кожного файлу, а не тільки тут.

**Немає автоматичного встановлення.** `systems/live.scm` дає завантажувальний ISO з інструментами всередині, але встановлення на диск лишається свідомою дією користувача: `wsm-guix-deploy` готує конфігурацію, далі `guix system init`. Автоматизувати це означає реалізувати крок `APPLY` з [INSTALLER-HANDOFF.md](INSTALLER-HANDOFF.md) — його поки немає.

**Немає nonfree firmware і драйверів.** Free-профіль не повинен залежати від Nonguix ([ADR 0003](decisions/0003-free-by-default.md)). Wi-Fi, відеокарти й частина периферії на вільних драйверах працюють не завжди; для них потрібен окремий профіль WSM Compatibility з рішенням по кожному компоненту за [ETHICS.md](ETHICS.md). Це не зроблено.

**Немає власного інсталятора з графічним інтерфейсом.** Вибір frontend-а — у [ADR 0006](decisions/0006-hardware-first-installer-frontend.md), реалізації немає.

## Як зібрати й перевірити

На машині з Guix, покроково, не перескакуючи:

```sh
# 1. Профіль описує систему — спершу він має побудуватися.
guix system build systems/desktop.scm

# 2. Завантаження без графіки: якщо ядро не стартує, це видно тут.
guix system vm --no-graphic systems/desktop.scm

# 3. Те саме з графікою — перевірка SDDM і KDE.
guix system vm systems/desktop.scm

# 4. Наш пакет окремо.
guix build -f wsm/packages/wsm.scm

# 5. ISO — regular file, окремий GC-root, manifest і SHA-256.
make image-live
```

Скрипт вимагає чистого Git worktree та використовує `channels.lock.scm` через
`guix time-machine`; WSM Guix-модулі підключаються через locked `-L` path.
Він не передає `--disable-authentication` і зупиняється, якщо у виводі
channel resolution/build явно з'являється `channel authentication disabled`.
Попередження `channel is not trusted` не приховується: воно фіксується
в `manifest.json` для окремої перевірки.

Результати за замовчуванням з'являються в `build/`:
- `wsm-desktop-live.iso` — звичайний regular ISO-файл, який можна передавати QEMU та публікувати як asset;
- `.wsm-desktop-live.iso-root` — окремий GC-root symlink на незмінний store object;
- `manifest.json` і `SHA256SUMS` — source commit, lock/profile hashes, resolved Guix channel, розмір і SHA-256 саме regular ISO;
- `channels.resolved.scm`, `channel-resolution.log` і `build.log` — channel/build evidence.

Перед публікацією builder перевіряє ISO9660 Primary Volume Descriptor (тип 1,
`CD001`, version 1 у секторі 16), тотожність байтів матеріалізованого файлу
образу зі store object і збіг resolved Guix channel commit із
`channels.lock.scm`. Команда `guix time-machine ... system image` використовує
`--save-provenance`, щоб записати походження системної конфігурації в образ.
Це structural/build-output validation, а не доказ завантаження.

Для іншого каталогу можна задати `WSM_ISO_DIR=/absolute/path`.
Для наступної спроби використовуйте новий порожній каталог: скрипт не перезаписує
попередні артефакти та журнали.

Цей script/test contract **не є доказом реального ISO build або boot**.
Потрібні Guix build на точному lock і окремий QEMU/OVMF test, який завантажує
цей самий ISO до робочої Plasma session.

Кожен крок має завершитися перед наступним. Успішна побудова **не** доводить, що система завантажується: саме на цьому проєкт уже спіткнувся — `guix system build` давав `exit=0`, а `--full-boot` через GRUB до ядра не дійшов.

## Приймання першого образу

Образ вважається зробленим не тоді, коли збірка повернула нуль, а коли гостьова
система **сама** сказала, що піднялася. Для цього `systems/live.scm` містить
службу, яка після старту пише в послідовну консоль маркер `WSM_LIVE_READY`.

Служба навмисно не валить завантаження: якщо консолі немає, маркер просто
відсутній, і перевірка каже «маркера немає», а не «система не стартує».

Обидва режими firmware обов'язкові — BIOS-only завантаження нічого не доводить
про UEFI-машини:

```sh
# BIOS
python3 scripts/qemu_boot_smoke.py --iso build/wsm-desktop-live.iso \
    --boot-marker WSM_LIVE_READY --timeout-seconds 300

# UEFI (потрібен OVMF)
python3 scripts/qemu_boot_smoke.py --iso build/wsm-desktop-live.iso \
    --firmware uefi --ovmf-code /usr/share/OVMF/OVMF_CODE.fd \
    --ovmf-vars /usr/share/OVMF/OVMF_VARS.fd \
    --boot-marker WSM_LIVE_READY --timeout-seconds 300
```

Для UEFI використовуйте пару `OVMF_CODE.fd` і `OVMF_VARS.fd` **з одного
пакета та однієї збірки OVMF**. CODE підключається read-only як pflash unit 0;
harness копіює лише окремий VARS template у приватний тимчасовий файл і
підключає копію writable як unit 1. Вихідні firmware inputs та NVRAM хоста
не змінюються. У JSON це позначено як
`host_efi_variables_modified=false` і
`guest_uefi_vars_writable=true`. Без будь-якого з `--ovmf-code` /
`--ovmf-vars`, або якщо файли порожні, є symlink чи вказують на той самий
файл, запуск відмовляє з кодом 2 — жодного неявного переходу на BIOS немає.

Важлива межа доказу: `WSM_LIVE_READY` означає лише, що base live-system
дійшла до Shepherd marker. Це **не** доказ запуску SDDM greeter чи активної
Plasma session (`plasmashell`/KWin). Для заяви про робочий KDE live desktop
потрібен окремий `WSM_PLASMA_SESSION_READY` marker з KDE autostart і окремий
QEMU-session check.

Критерій NO-GO: збірка успішна, але маркера немає в жодному або в одному з
режимів.

## Припущення, які треба перевірити першими

Ці місця найімовірніше не збігатимуться з реальним Guix, і кожне ламає збірку:

1. ~~`sddm-configuration` з полем `display-server`~~ — **перевірено й виправлено.** У Guix значення `"wayland"` для `sddm-service-type` відоме як зламане: екран лишається чорним (Guix bug#68939), а патч bug#70527 змушує службу ігнорувати це значення й використовувати x11. У профілі тепер типовий x11 без явного поля.
2. ~~`bluetooth-configuration` з полем `auto-enable?`~~ — **перевірено.** Поле існує, типове значення `#f`, що збігається з наміром профілю: радіо не вмикається без потреби.
3. ~~`plasma-desktop-service-type`~~ — **перевірено.** Служба існує в `(gnu services desktop)`, її значення — `plasma-desktop-configuration`. GNU Guix 1.5 (січень 2026) постачає KDE Plasma 6.5 і саме цю службу. Невикористаний імпорт `(gnu packages kde-plasma)` прибрано: пакет `plasma` приходить через службу. Що саме буде в зібраному образі, вирішує зафіксована ревізія каналу — це перевіряється на `channels.lock.scm`, а не тут.
4. ~~`(include "desktop.scm")`~~ — **виправлено.** `include` з відносним шляхом залежить від того, з якого каталогу запущено `guix`. Замінено на явне `load` з шляхом від `(current-filename)`, тож результат не залежить від робочого каталогу.
5. ~~`(local-file "../.." ...)`~~ — **перевірено й виправлено.** `local-file` резолвить відносний шлях відносно файлу, де форма записана (підтверджено в guix/gexp.scm і в листі Ludovic Courtès), тож `"../.."` справді вказує на корінь репозиторію. Але без `select?` у store потрапляв би весь `.git` — додано фільтр на `.git`, `__pycache__` і `build`.

Якщо щось не збігається — правити у файлі, а не в цьому документі.

## Що робить `tests/test_system_profiles.py`

Тести не збирають нічого й не вдають, що можуть. Вони перевіряють дві речі:

- кожен `.scm` читається як послідовність **завершених** s-виразів — це ловить обрізаний файл, який Guix не візьме;
- у профілях справді написано те, що вони обіцяють: рівно один дисплейний менеджер, KDE, шрифти з кирилицею, українська локаль, жодної залежності від Nonguix.

Це не замінює `guix system build`. Це лише дешевий запобіжник від найпоширенішої поломки в цьому репозиторії — файлу, записаного наполовину.