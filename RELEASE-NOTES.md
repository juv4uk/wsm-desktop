# WSM Desktop Hardware Preview RC1

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Версія: `0.1.0-rc1` (`RELEASE-INFO.json`)
- Дата: 2026-11-25
- Статус: **pre-release / hardware evidence only**
- Вихідний коміт: див. `release-manifest.json` у релізних артефактах

## Що це є

Це read-only релізний кандидат для збору апаратних доказів на Linux-ПК. Він **не встановлює WSM Desktop** і не змінює систему поза явно вибраним output-каталогом. Він виконує чотири речі:

1. `wsm-hwcheck` 0.2.0 читає локальні `/sys` і `/proc`; стандартно додає runtime-діагностику з `/lib/modules/<kernel>/modules.*` і фіксованих команд лише для читання `journalctl -k -b --no-pager --output=cat --lines=4096` / `dmesg --color=never`. Якщо дані недоступні без прав, поле лишається `unknown` і з'являється warning.
2. `wsm-install --preflight --dry-run` валідує цей звіт і видає **diagnostic-only** план для ратифікованого backend-а `guix-system`; план `nixos` лишається лише дослідницьким.
3. `scripts/wsm_hardware_check.py` перевіряє `plan_status`, `plan_mode`, `plan_readiness.confirmable=false`, збіг `backend.id`, digest-и, а також що `dry_run=true`, `mutations_authorized=false`, `backend_invoked=false`, `disk_access_performed=false`, після чого пише manifest і `SHA256SUMS`. Команди в manifest зберігаються як argv-масиви з `<out>` замість абсолютних шляхів.
4. `channels.lock.scm` фіксує автентифіковані метадані вільного офіційного Guix-каналу. Для цього lock підтверджено authenticated `guix pull` і `time-machine ... describe`; збірку або запуск VM із цим самим lock у межах RC1 ще не підтверджено.

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

Раніший знімок у [systems/README.md](systems/README.md) справді було отримано з вимкненою автентифікацією як дослідницький checkout. Цей lock — окремий автентифікований pull того самого коміту в ізольованому профілі. `guix time-machine` може попереджати «channel is not trusted», бо локальний channels-файл не внесено до `trusted-channels.scm`; це не повідомлення про failing signature. `--disable-authentication` не використовувався, `time_machine_exit=0`.

Цей lock є зафіксованим автентифікованим channel input, але не доказом збірки чи завантаження системи саме з нього. Команди вище наведено як спосіб провести таку окрему перевірку; їхні успішні результати не заявляються в цьому RC.

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