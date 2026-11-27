# WSM Desktop — публікація ISO

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Реліз `0.1.0-rc2-live-iso` містить assets Free hardened ISO та шість базових
частин Compatibility/NVIDIA ISO. Наявність Compatibility parts у GitHub Release
підтверджена повторною перевіркою Release API 28.11.2026; це виправляє попередній
стан документа, який помилково називав їх лише локальним кандидатом.

**Публікація asset ≠ ліцензійне схвалення ≠ доказ походження ≠ апаратна сертифікація.**
Для Compatibility/NVIDIA binary payload redistribution status залишається
`NOT CLEARED`: NVIDIA EULA §1.1(d) містить умову щодо незмінених binary files,
а pinned Nonguix recipe виконує `patchelf` над ELF у driver package. Це не
юридичний висновок щодо конкретного archive 580.178.04. Не створювати нові
дзеркала, повторні завантаження чи релізи цих binary assets до перевірки точного
bundled EULA та окремого licensing review. Рішення про вже опубліковані assets
не приймається цим документальним виправленням.

GitHub обмежує один release asset до 2 GiB, тому ISO розбивається на частини.
Загальний розмір релізу не обмежений; бінарні частини не додаються до Git-історії.

## Склад релізу

| Адаптер | Статус у GitHub Release | Ім'я ISO | Розмір | SHA-256 |
| --- | --- | --- | ---: | --- |
| Free, hardened | Опубліковано частинами | `wsm-desktop-kde-hardened-20261125.iso` | 8303056896 | `d1a000f8c465b496565b0f611ae6f65095086a8457c663f212ca5b17073fd7ef` |
| Free, hardened (з консольним доступом) | Опубліковано частинами | `wsm-desktop-kde-hardened-20261126-login.iso` | 8277964800 | `deec276886656b99c3f3f58e51d9fd3fc89baf814e38e5f6e9ddc704976b17f7` |
| Compatibility/NVIDIA | 6 базових `.partNNN` assets присутні в RC2; redistribution NOT CLEARED | `wsm-desktop-kde-compat-nvidia-20261126.iso` | 10382727168 | `19a1ca6fc1377fbfb878e1cf670fc521faf7ea0389579f3a6501d956b6df6da0` |
| Compatibility/NVIDIA (з консольним доступом) | Локальний кандидат; до RC2 не завантажений | `wsm-desktop-kde-compat-nvidia-20261126-login.iso` | 10382725120 | `41486ff5c86db95c63a45c7fb1cf753e604eb97fef1f777093c4325a4edebd60` |

Частини мають вигляд `<ім'я ISO>.part001`, `.part002`, … і кожна менша за 2 GiB.
GitHub Release API для `0.1.0-rc2-live-iso` підтверджує шість базових
Compatibility assets станом на 28.11.2026:

| Asset | Розмір (байт) | GitHub API SHA-256 |
| --- | ---: | --- |
| `.part001` | 1992294400 | `909c33c038ab8504a4782f741ec13f6063335606f6db7051675d75436fc9f517` |
| `.part002` | 1992294400 | `98e8e71a2ba1eb931c13dbeee926424c2e0380392a8447828af7d8e8b2e209eb` |
| `.part003` | 1992294400 | `9f7d1d274efe494bf94c522ec688f24d41d6e0ec86c006afc9f281c9d9009dd0` |
| `.part004` | 1992294400 | `6ac5a190260543e315c0e80efa26d258463f3879918bf1f1fed95bcaac6d8a19` |
| `.part005` | 1992294400 | `2e4c4ab45a6acdb42506f6352f6de51b48e90f21059f227b415aaeeaade7926d` |
| `.part006` | 421255168 | `557e8f1f3baa6456bf6cd6fe5ef28df424a42e1df58f300b22bedb6349cbb33a` |

П'ять перших частин мають по 1992294400 байт, остання — 421255168 байт; сума
розмірів дорівнює 10382727168 байт із таблиці. GitHub API також повертає
`SHA256SUMS-compat` та `ISO-CHECKSUMS.sha256`. Однак у фактичному asset list
RC2 **немає `release-manifest.json`**, тому `source_commit` для цих Compatibility
parts не можна підтвердити за релізним manifest і він лишається `unknown`.
Наведені digest-и — значення asset metadata GitHub API; повне завантаження,
повторне складання та звіряння із `SHA256SUMS-compat` у цій перевірці не
виконувалися. Не позначати цей Compatibility образ як artifact-verified.

Локальне зворотне складання шести частин раніше перевірялося
`scripts/reassemble-iso.sh`; це свідчення локального кандидата, а не доказ, що
опубліковані частини мають той самий source commit. Для Compatibility `-login`
варіанта частин у RC2 немає. Приклад завантаження нижче лишається для Free
hardened ISO; наявність Compatibility parts не знімає `redistribution NOT CLEARED`.

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
- оновлені `-login`-образи: консольний логін `wsm`, пароль `wsm` (SHA-512 crypt
  у профілі), користувач у групі `wheel`, тому `sudo` запитує той самий пароль;
  порожній пароль заборонено (`allow-empty-passwords? #f`);
- compatibility ISO: `linux-wsm-gp107-7.3.5`, NVIDIA **580.178.04**,
  `nvidia-firmware` і `linux-firmware` для GTX 1050 Ti (Pascal `GP107`, `sm_61`).

## Compatibility ISO: фактичні докази збірки

Початкова збірка завершилася 26.11.2026 о 17:57 EET, оновлена `-login`-версія —
о 22:45 EET, у ізольованому Guix store (`ns-m1`, pinned `guix 4e5195be…` +
Nonguix `6b8897c…`). Замість загального `linux 7.3.5` використано
`gnu-linux:customize-linux` із `localmodconfig` і whitelist
`systems/wsm-gp107.modconfig`: **69 модулів** замість 6519 у базовій
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
у serial-консолі з'явилися `WSM_LIVE_READY`, `This is the GNU system.` і
`wsm-kde login:`. У `-login`-версії після вводу `wsm`/`wsm` відкривається
`wsm@wsm-kde ~$`, а `sudo -S id -u` повертає `0`. У ранньому лозі гостя також є
рядок про segfault Guile в `init`, але подальший старт shepherd і досягнення
login-підказки зафіксовано. TCG не емулює GTX 1050 Ti, тому цей запуск **не є**
доказом роботи NVIDIA на реальному GPU; для цього потрібен перший boot із
Ventoy на цільовій машині.

Поточний Compatibility build використовує NVIDIA **580.178.04** і Linux
**7.3.5**. Після цього build NVIDIA опублікувала 580.196.11 (23.11.2026),
яка офіційно перелічує GeForce GTX 1050 Ti; stable Linux 7.3.6 також вийшов
23.11.2026. Це лише кандидати для наступного build: поточний ISO не містить цих
версій, а їх сумісність треба окремо підтвердити Guix/Nonguix evaluation,
module build, rebuild ISO та повторним BIOS/UEFI й physical acceptance.

NVIDIA License: [Driver License Agreement](https://www.nvidia.com/en-us/drivers/nvidia-license/),
§1.1(d) та §2.3. Базові Compatibility `.part001`–`.part006` уже присутні у
RC2 Release, але їхній redistribution status лишається `NOT CLEARED`; факт
наявності asset-ів не є ліцензійним висновком. До завершення окремого review не
повторно розповсюджувати, дзеркалити або перепаковувати ці binary payloads.

Джерела: [NVIDIA 580.196.11](https://www.nvidia.com/en-us/drivers/details/285683/),
[NVIDIA legacy GPU support timeframe](https://nvidia.custhelp.com/app/answers/detail/a_id/3142/),
[Linux 7.3.6 stable](https://kernel.googlesource.com/pub/scm/linux/kernel/git/stable/linux/%2B/refs/tags/v7.3.6).

Старий `wsm-desktop-kde-20261125.iso` з SHA `c054c6f7...` лишається на Ventoy
лише як історичний boot-доказ і **не є** релізним артефактом.

## Межі

Наскрізна інсталяція з записом на диск лишається за #112. Реліз є prerelease:
hardened boot перевірено в QEMU, але повний bare-metal proof на реальній GPU
і власника Plasma-сеансу ще треба підтвердити окремо.
