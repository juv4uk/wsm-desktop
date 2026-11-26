# WSM Desktop — публікація ISO

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Реліз `0.1.0-rc2-live-iso` містить наші власні завантажувальні образи WSM Desktop.
GitHub обмежує один release asset до 2 GiB, тому ISO розбито на частини. Загальний
розмір релізу не обмежений; бінарні частини не додаються до Git-історії.

## Склад релізу

| Адаптер | Ім'я в релізі | Розмір | SHA-256 |
| --- | --- | ---: | --- |
| Free, hardened | `wsm-desktop-kde-hardened-20261125.iso` | 8303056896 | `d1a000f8c465b496565b0f611ae6f65095086a8457c663f212ca5b17073fd7ef` |
| Compatibility/NVIDIA | `wsm-desktop-kde-compat-nvidia-20261126.iso` | див. `ISO-CHECKSUMS.sha256` | див. `ISO-CHECKSUMS.sha256` |

Частини мають вигляд `<ім'я ISO>.part001`, `.part002`, … і кожна менша за 2 GiB.
Повний набір контрольних сум лежить у `ISO-CHECKSUMS.sha256` релізу.

## Збирання ISO з частин

```sh
gh release download 0.1.0-rc2-live-iso \
  --pattern 'wsm-desktop-kde-hardened-20261125.iso.part*' \
  --dir ./wsm-iso
sh scripts/reassemble-iso.sh \
  ./wsm-iso/wsm-desktop-kde-hardened-20261125.iso \
  ./wsm-desktop-kde-hardened-20261125.iso \
  ./wsm-iso/SHA256SUMS
```

Скрипт збирає частини по черзі й звіряє кінцевий SHA-256. Для Ventoy одразу
можна використати вже зібраний файл `D:\wsm-desktop-kde-hardened-20261125.iso`.

## Що саме в цих образах

- KDE Plasma + SDDM, NetworkManager/WPA, serial console;
- наші `wsm-hwcheck`, `wsm-install` і `wsm-install-live` (read-only preflight);
- hardened free ISO: `(password #f)`, без `wheel`, з `allow-empty-passwords? #f`;
- compatibility ISO: `linux 7.3.5`, NVIDIA **580.178.04**, `nvidia-firmware` і
  `linux-firmware` для GTX 1050 Ti (Pascal `GP107`, `sm_61`).

Старий `wsm-desktop-kde-20261125.iso` з SHA `c054c6f7...` лишається на Ventoy
лише як історичний boot-доказ і **не є** релізним артефактом.

## Межі

Наскрізна інсталяція з записом на диск лишається за #112. Реліз є prerelease:
hardened boot перевірено в QEMU, але повний bare-metal proof на реальній GPU
і власника Plasma-сеансу ще треба підтвердити окремо.
