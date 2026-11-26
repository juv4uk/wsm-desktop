# WSM Desktop RC4 — інсталятор у режимі попереднього перегляду

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Версія: `0.1.0-rc4` (`RELEASE-INFO.json`)
- Дата: 2026-11-26
- Статус: **pre-release / preview-only; команди інсталяції не виконуються**
- Вихідний коміт: буде зафіксований у `release-manifest.json` під час побудови цього RC після злиття змін.

## Що уточнено від RC3

Цей кандидат виправляє твердження про стан інсталятора та узгоджує метадані з кодом після #312. Він **не додає APPLY** і не перетворює прототип на підтримуваний інсталятор.

| Вхід | Фактична поведінка в RC4 |
| --- | --- |
| `wsm-install --guided` | Read-only preflight і показ плану; без виконання кроків |
| `wsm-install --tui` | Той самий planner та preview-only executor |
| Calamares `wsm_deploy` | Опційний preview-модуль; required job повертає failure, бо WSM не встановлено |
| `wsm-install-agent` | Перевіряє структуру плану та показує preview; не запускає зовнішні процеси |

**APPLY вимкнено в усіх входах.** `wsm_install.executor.execute()` відхиляє `dry_run=False`. Для кожного запланованого кроку результат має `status: "not-run"` і пояснення, що команда не виконувалася. Команди `partprobe`, `udevadm`, `mkfs.*`, `mount`, `mkdir` у валідаторі агента — це перелік розпізнаваних форм плану, а не дозвіл на виконання.

**Журнал і відновлення.** Код журналу та recovery report входить до репозиторію, однак preview-only executor не запускає інсталяційні кроки. Тому цей RC не містить результату реального встановлення, відмови після disk write або перевіреного відновлення диска.

**Єдиний системний backend.** Для першого підтримуваного шляху обрано GNU Guix (ADR 0004). Nix/NixOS не є альтернативним backend-ом цього RC. Наявність діагностичних або дослідницьких Nix-артефактів не змінює цього рішення.

## Межі доказів цього RC

- Hardware collector працює лише для читання; інвентаризація не доводить функціональність драйвера чи firmware.
- QEMU guest acceptance перевіряє окремі сценарії harness-а, включно з віртуальними пристроями. Це не доводить сумісність фізичного ПК.
- Синтетичний ISO у CI harness не є релізним WSM ISO і не підтверджує побудову чи завантаження desktop-образу.
- Жодна інсталяція не виконана — ні в QEMU, ні на фізичному обладнанні.
- Фізичні benchmark-и не виконувалися; тверджень про перевагу продуктивності немає.

## Guix channel inputs

`channels.lock.scm` та `channels/compatibility.lock.scm` — окремі зафіксовані входи каналів. Перевірка `scripts/check_channels.py` підтверджує структурну політику lock-файлу, але **структурна перевірка не є криптографічною автентифікацією**.

Автентифікацію конкретного lock-файлу може підтвердити лише окремий успішний запуск Guix release gate на точному джерелі, зокрема `guix time-machine -C <lock> -- describe -f channels`, із збереженими результатом і точним SHA. Відсутність такого результату, пропущений крок або лише structural PASS не дають права називати канал автентифікованим. `--disable-authentication` не є допустимим способом отримати цей доказ.

## Артефакти RC4

Після злиття та перевірки точного commit побудова `scripts/build_release_bundle.py` має створити:

- `wsm-desktop-0.1.0-rc4-source.tar.gz`;
- `SHA256SUMS`;
- `release-manifest.json` з точним `source_commit` і SHA-256 артефактів.

Опублікований RC3 і його tag/source archive не змінюються. Цей PR лише готує метадані наступного кандидата; він сам по собі не публікує реліз.

## Що змінилося від RC1 (архів)
**Ліцензія.** Робота проєкту перейшла з GPL-3.0-or-later (код) і CC-BY-SA-4.0
(документація) на власну ліцензію **ВОЛЬНІСТЬ**. Це стосується RC2 і далі.
Той, хто вже взяв RC1, отримав його під GPL-3.0-or-later і CC-BY-SA-4.0 — та
ліцензія не відкликається і лишається чинною для тих артефактів.

**Десктоп.** Додано `systems/desktop.scm` (KDE Plasma, SDDM як єдиний
дисплейний менеджер, NetworkManager, звук, шрифти з кирилицею, українська
локаль) і `systems/live.scm` з `scripts/build_iso.sh`. **Це рецепти, а не
образ:** жоден із них не зібрано, бо в середовищі написання немає Guix.
У реліз вони входять як вихідний текст із явною позначкою «не перевірено».

**Захист релізної збірки.** `build_release_bundle.py` відмовляється збирати
артефакт під іменем, відмінним від канонічного: інакше `SHA256SUMS` посилався б
на файл, якого ніхто не завантажує, і перевірка контрольної суми падала б тихо.

**Запобіжник проти обрізаних файлів.** `tests/test_python_syntax.py` парсить
кожен `.py` у репозиторії. За одну добу чотири pull request прийшли з файлом,
записаним наполовину; тепер це червона перевірка, а не зламаний релізний
інструмент.

**Безпека.** Обмежено initramfs і serial-вивід у CXL QEMU guest; додано
перевірку стану Guix-плану (`mountinfo`, digest); DisplayID parser вимкнено за
замовчуванням до підтвердженого upstream-виправлення.

**Документація.** ADR 0006 (hardware-first frontend) і реєстр рішень;
дослідницькі документи позначено як такі, що не блокують реліз; мовна політика
зафіксована — українська канонічна, англійська як `.en.md`.

## Що це є

Це read-only релізний кандидат для збору апаратних доказів на Linux-ПК. Він **не встановлює WSM Desktop** і не змінює систему поза явно вибраним output-каталогом. Він виконує чотири речі:

1. `wsm-hwcheck` 0.2.0 читає локальні `/sys` і `/proc`; стандартно додає runtime-діагностику з `/lib/modules/<kernel>/modules.*` і фіксованих команд лише для читання `journalctl -k -b --no-pager --output=cat --lines=4096` / `dmesg --color=never`. Якщо дані недоступні без прав, поле лишається `unknown` і з'являється warning.
2. `wsm-install --preflight --dry-run` валідує цей звіт і видає **diagnostic-only** план для ратифікованого backend-а `guix-system`; план `nixos` лишається лише дослідницьким.
3. `scripts/wsm_hardware_check.py` перевіряє `plan_status`, `plan_mode`, `plan_readiness.confirmable=false`, збіг `backend.id`, digest-и, а також що `dry_run=true`, `mutations_authorized=false`, `backend_invoked=false`, `disk_access_performed=false`, після чого пише manifest і `SHA256SUMS`. Команди в manifest зберігаються як argv-масиви з `<out>` замість абсолютних шляхів.
4. `channels.lock.scm` є зафіксованим входом офіційного Guix-каналу. Історичний опис окремого authenticated pull у RC1 не замінює release-gate результат для точного source commit; structural policy та наявність pin самі по собі не доводять криптографічну автентифікацію.

Покрокова інструкція для реального заліза — у [docs/RELEASE-TESTING.md](docs/RELEASE-TESTING.md).

## Що можна перевірити на своєму ПК

- чи визначається ваша конфігурація CPU/GPU/storage/network/input у звіті;
- чи не містить звіт заборонених ідентифікаторів (serial, MAC, UUID, WWN, hostname, username, IP);
- чи видає Guix безпечний diagnostic-only план, а Nix-план не виходить за межі дослідження;
- чи з'являються зрозумілі `blockers`/`warnings` замість тихого «успіху»;
- чи збігаються checksums завантаженого tarball із опублікованими.

## Що прямо заборонено в цьому RC

- немає завантажувального ISO/USB-інсталятора;
- немає `guix system init`, `nixos-install`, форматування, монтування чи зміни розділів;
- немає запису поза явним output-каталогом, зокрема в `/dev`, `/sys`, `/proc`, EFI або bootloader хоста;
- немає викликів Guix/Nix backend-у з метою розгортання;
- немає мережевих запитів чи завантаження драйверів/firmware;
- немає Nonguix або nonfree firmware у `channels.lock.scm`;
- немає другого підтримуваного backend-а: [ADR 0004](docs/decisions/0004-nix-guix-backend-strategy.md) ратифіковано 25.11.2026 для GNU Guix, а Nix/NixOS лишається дослідженням у [#55](https://github.com/juv4uk/wsm-desktop/issues/55).

## Channel lock

`channels.lock.scm` створено з ізольованого профілю, де `guix pull` виконувався **без** `--disable-authentication`. Lock містить `make-channel-introduction` і коміт `4e5195be20d9b124df8a8bb69213412236e4668e`; докази — у [#39](https://github.com/juv4uk/wsm-desktop/issues/39). Це вільний набір каналів: тільки офіційний Guix, без Nonguix і додаткових ключів чи substitute serverів.

Відтворення:

```sh
guix time-machine -C channels.lock.scm -- describe -f channels
guix time-machine -C channels.lock.scm -- system build systems/minimal.scm
guix time-machine -C channels.lock.scm -- system vm --no-graphic systems/minimal.scm
```

Раніший знімок у [systems/README.md](systems/README.md) справді було отримано з вимкненою автентифікацією як дослідницький checkout. Окремий історичний authenticated pull у RC1 стосується лише того експерименту й не є доказом проходження актуального release gate для точного source commit. `guix time-machine` має виконувати перевірку з автентифікацією; `--disable-authentication` не є допустимим обхідним шляхом.

Наявність pin і проходження structural policy не доводять криптографічну автентифікацію чи збірку/завантаження системи. Для автентифікації потрібен окремий успішний Guix release-gate запуск на точному lock; для build/boot — окремі результати команд із точним SHA та логами. Результати, яких немає, позначаються як not-run, а не як PASS.

## Підтверджені межі

Попередній QEMU/TCG boot мінімального Guix System із маркером `wsm-desktop login:` описано в [systems/README.md](systems/README.md), але він походить з окремого shallow checkout, отриманого з вимкненою автентифікацією. Тому цей результат **не** зараховується як build/boot proof для `channels.lock.scm`. Щоб отримати такий доказ, потрібно окремо успішно виконати `guix time-machine -C channels.lock.scm -- system build systems/minimal.scm` і `guix time-machine -C channels.lock.scm -- system vm --no-graphic systems/minimal.scm`, зберегти точні exit codes та логи. Повний GRUB `--full-boot` до ядра також не доведено, тому це **не** доказ завантаження з реального USB.

NixOS-експеримент для #55 має `nix_build_exit=0`. Окремий boot у QEMU/TCG дійшов до systemd-маркерів `Reached target Login Prompts` і `Reached target Multi-User System`, але завершився `vm_exit=124` за timeout 420 і не видав маркера `login:`. Логи й точні exit codes публікуються окремо в [#55](https://github.com/juv4uk/wsm-desktop/issues/55); це не є частиною обіцянки цього RC.

## Відомі обмеження

- `wsm-hwcheck` 0.2.0 зі схемою звіту 1.0.0 — inventory-only: він не виконує функціональних тестів і не доводить ініціалізацію firmware чи працездатність драйвера.
- `wsm-install` 0.1.0 завжди повертає `diagnostic-only`; у нього немає режиму apply або підтвердження плану.
- `plan_readiness.confirmable=false` навіть тоді, коли список `blockers` порожній: вибір цільового диска завжди лишається за користувачем і перевіряється окремо.
- Звіт може містити model/manufacturer пристроїв. Це не секрети, але перед публічним постом зробіть окрему санітизовану копію; на корпоративному ноуті чутливі деталі варто надіслати приватно.

## Як перевірити цілісність

Завантажте `wsm-desktop-0.1.0-rc1-source.tar.gz`, `SHA256SUMS` і `release-manifest.json` з одного релізу:

```sh
sha256sum -c SHA256SUMS
python3 -c 'import json; d=json.load(open("release-manifest.json")); n="wsm-desktop-0.1.0-rc1-source.tar.gz"; print(d["source_commit"], d["artifacts"][n]["sha256"])'
```

Tarball побудовано з `git archive HEAD | gzip -n -9` (`mtime=0`), тобто однаковий коміт дає однакові байти. `release-manifest.json` містить точний `source_commit` і розміри артефактів.

## Зворотний зв'язок

Додайте до [#10](https://github.com/juv4uk/wsm-desktop/issues/10) або [#8](https://github.com/juv4uk/wsm-desktop/issues/8):

- версію/release ID з `manifest.json`;
- `overall` і статуси `guix`/`nix`;
- стислий human-readable summary зі stderr;
- модель пристрою/проблему, але **не** сирі serial/MAC/UUID/WWN.

Не надсилайте `report.json` публічно без попередньої перевірки: хоча v1 має redactions, публічний звіт може розкрити модель обладнання або середовище. За потреби підготуйте санітизований фрагмент і надішліть його приватно.