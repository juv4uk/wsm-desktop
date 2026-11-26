# WSM Desktop — публікація ISO

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Реліз `0.1.0-rc2-live-iso` містить наші власні завантажувальні образи WSM Desktop.
GitHub обмежує один release asset до 2 GiB, тому ISO розбито на частини. Загальний
розмір релізу не обмежений; бінарні частини не додаються до Git-історії.

## Склад релізу

| Адаптер | Ім'я в релізі | Розмір | SHA-256 |
| --- | --- | ---: | --- |
| Free, hardened (з консольним доступом) | `wsm-desktop-kde-hardened-20261126-login.iso` | 8277964800 | `deec276886656b99c3f3f58e51d9fd3fc89baf814e38e5f6e9ddc704976b17f7` |
| Compatibility/NVIDIA (з консольним доступом) | `wsm-desktop-kde-compat-nvidia-20261126-login.iso` | 10382725120 | `41486ff5c86db95c63a45c7fb1cf753e604eb97fef1f777093c4325a4edebd60` |
| Free, hardened (попередній) | `wsm-desktop-kde-hardened-20261125.iso` | 8303056896 | `d1a000f8c465b496565b0f611ae6f65095086a8457c663f212ca5b17073fd7ef` |
| Compatibility/NVIDIA (попередній) | `wsm-desktop-kde-compat-nvidia-20261126.iso` | 10382727168 | `19a1ca6fc1377fbfb878e1cf670fc521faf7ea0389579f3a6501d956b6df6da0` |

Частини мають вигляд `<ім'я ISO>.part001`, `.part002`, … і кожна менша за 2 GiB.
Нові `-login`-образи мають власні частини; контрольні суми лежать у
`SHA256SUMS-login`, суми всіх релізних ISO — у `ISO-CHECKSUMS.sha256`.
Суми попередніх частин лишаються в `SHA256SUMS` і `SHA256SUMS-compat`.
Зворотне складання перевіряється `scripts/reassemble-iso.sh`.

## Збирання ISO з частин

```sh
gh release download 0.1.0-rc2-live-iso \
  --pattern 'wsm-desktop-kde-hardened-20261126-login.iso.part*' \
  --dir ./wsm-iso
sh scripts/reassemble-iso.sh \
  ./wsm-iso/wsm-desktop-kde-hardened-20261126-login.iso \
  ./wsm-desktop-kde-hardened-20261126-login.iso \
  ./wsm-iso/SHA256SUMS-login
```

Скрипт збирає частини по черзі й звіряє кінцевий SHA-256. Для Ventoy одразу
можна використати вже зібраний файл `D:\wsm-desktop-kde-hardened-20261126-login.iso`.

## Що саме в цих образах

- KDE Plasma + SDDM, NetworkManager/WPA, serial console;
- наші `wsm-hwcheck`, `wsm-install` і `wsm-install-live` (read-only preflight);
- обидва оновлені ISO: консольний логін `wsm`, пароль `wsm` (SHA-512 crypt у
  профілі), користувач у групі `wheel`, тому `sudo` запитує той самий пароль;
  порожній пароль заборонено (`allow-empty-passwords? #f`);
- compatibility ISO: `linux-wsm-gp107-7.3.5`, NVIDIA **580.178.04**,
  `nvidia-firmware` і `linux-firmware` для GTX 1050 Ti (Pascal `GP107`, `sm_61`).

## Compatibility ISO: фактичні докази збірки

Оновлена збірка завершилася 26.11.2026 о 22:45 EET у ізольованому Guix store
(`ns-m1`, pinned `guix 4e5195be…` + Nonguix `6b8897c…`). Замість загального
`linux 7.3.5` використано `gnu-linux:customize-linux` із `localmodconfig` і
whitelist `systems/wsm-gp107.modconfig`: **69 модулів** замість 6519 у базовому
конфігурації. `nouveau`, `gma500`, `i915` вимкнено; архітектура лишається
`x86-64 generic`. Щоб уникнути несумісності generic initrd із таким ядром,
`initrd-modules` явно обмежено модулями, які ядро справді містить; NVMe/ext4
вбудовані в ядро.

Перевірено безпосередньо в ISO:

- `grub.cfg` містить `console=ttyS0,115200`, `modprobe.blacklist=nouveau`,
  `nvidia-drm.modeset=1`;
- `nvidia.ko`, `nvidia-drm.ko`, `nvidia-uvm.ko`, `nvidia-modeset.ko` і
  `nvidia-peermem.ko` версії **580.178.04** лежать у
  `/lib/modules/7.3.5/updates/` (як `.ko.zst`);
- `modinfo` показує універсальні PCI-class aliases `pci:v000010DEd*…`, тобто
  прив'язка до `0x1c82` іде через NVIDIA PCI class, а не явний device-id;
- `linux-firmware` містить каталог `nvidia/gp107` (`acr`, `gr`, `nvdec`, `sec2`).

QEMU **TCG-only** (`q35,accel=tcg`, без KVM і без мережі) підтвердив завантаження:
у serial-консолі з'явилися `WSM_LIVE_READY`, `This is the GNU system.`,
`wsm-kde login:`; після вводу `wsm`/`wsm` відкривається shell
`wsm@wsm-kde ~$`, а `sudo -S id -u` повертає `0`. У ранньому лозі гостя також є рядок про segfault Guile в
`init`, але подальший старт shepherd і досягнення login-підказки зафіксовано.
TCG не емулює GTX 1050 Ti, тому цей запуск **не є** доказом роботи NVIDIA на
реальному GPU; для цього потрібен перший boot із Ventoy на цільовій машині.

Старий `wsm-desktop-kde-20261125.iso` з SHA `c054c6f7...` лишається на Ventoy
лише як історичний boot-доказ і **не є** релізним артефактом.

## Межі

Наскрізна інсталяція з записом на диск лишається за #112. Реліз є prerelease:
hardened boot перевірено в QEMU, але повний bare-metal proof на реальній GPU
і власника Plasma-сеансу ще треба підтвердити окремо.
