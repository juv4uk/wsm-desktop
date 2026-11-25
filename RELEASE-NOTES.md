# WSM Desktop Hardware Preview RC1

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Версія: `0.1.0-rc1` (`RELEASE-INFO.json`)
- Дата: 2026-11-25
- Статус: **pre-release / hardware evidence only**
- Вихідний коміт: див. `release-manifest.json` у релізних артефактах

## Що це є

Це перший релізний кандидат, який можна безпечно запустити на реальному обладнанні. Він **не встановлює WSM Desktop** і не змінює систему поза явним output-каталогом. Він виконує чотири речі:

1. `wsm-hwcheck` 0.2.0 читає локальні `/sys` і `/proc`; стандартно додає runtime-діагностику з `/lib/modules/<kernel>/modules.*` і фіксованих команд лише для читання `journalctl -k -b --no-pager --output=cat --lines=4096` / `dmesg --color=never`. Якщо дані недоступні без прав, поле лишається `unknown` і з'являється warning.
2. `wsm-install --preflight --dry-run` валідує цей звіт і видає **diagnostic-only** план для ратифікованого backend-а `guix-system`; план `nixos` лишається лише дослідницьким.
3. `scripts/wsm_hardware_check.py` перевіряє `plan_status`, `plan_mode`, `plan_readiness.confirmable=false`, збіг `backend.id`, digest-и, а також що `dry_run=true`, `mutations_authorized=false`, `backend_invoked=false`, `disk_access_performed=false`, після чого пише manifest і `SHA256SUMS`. Команди в manifest зберігаються як argv-масиви з `<out>` замість абсолютних шляхів.
4. `channels.lock.scm` фіксує автентифікований вільний канал Guix. Для цього RC підтверджені автентифікований pull та успішний `time-machine describe`; це ще не доказ build або VM boot саме з цього lock.

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

Команди для незалежної перевірки цього lock:

```sh
guix time-machine -C channels.lock.scm -- describe -f channels
guix time-machine -C channels.lock.scm -- system build systems/minimal.scm
guix time-machine -C channels.lock.scm -- system vm --no-graphic systems/minimal.scm
```

У поточному release evidence підтверджено лише першу команду (`time_machine_exit=0`). Дві наступні команди наведені як кроки майбутньої незалежної перевірки; їхній успіх для цього exact lock не заявляється.

Раніший знімок у [systems/README.md](systems/README.md) справді було отримано з вимкненою автентифікацією як дослідницький checkout. Цей lock — окремий автентифікований pull того самого коміту в ізольованому профілі: `--disable-authentication` не використовувався, `pull_exit=0`, а `time_machine_exit=0` для `describe`.

`guix time-machine` може показати «channel is not trusted», якщо локальний channels-файл не внесено до користувацького `trusted-channels.scm`. Це локальний trust-policy сигнал, який не слід ігнорувати, але він не тотожний помилці перевірки commit signature під час authenticated pull. У цьому RC підтверджено автентифіковане отримання та опис revision; успішний `system build` або VM boot саме з цього lock поки не заявляється.

## Підтверджені межі

Окремий попередній boot-доказ для мінімального Guix System у disposable QEMU/TCG зафіксований у [systems/README.md](systems/README.md): `guix system build` і `guix system vm` завершилися з `exit=0`, guest дійшов до `wsm-desktop login:`, QEMU завершився `vm_exit=0`. Той експеримент використовував попередній shallow checkout із вимкненою автентифікацією; його не можна трактувати як build/boot proof саме для `channels.lock.scm` цього RC. Повний GRUB `--full-boot` до ядра не доведено, тому це **не** доказ завантаження з реального USB.

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
