# Перший завантажувальний WSM KDE ISO

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

Це окремий live-image трек за #169/#170. Він **не змінює** опублікований
`0.1.0-rc1`: той лишається source-only hardware preview.

## Що зібрано

- Профіль: [`systems/live-iso.scm`](../systems/live-iso.scm), база — `bare-bones` Guix.
- Тип образу: `uncompressed-iso9660` (звичайний `iso9660` додає zisofs level 9
  і на цій машині стискався понад 35 хвилин).
- Розмір: 8 302 909 440 байт (7,73 GiB), `file` → bootable ISO 9660.
- SHA-256: `c054c6f7af5119f96739cdab4fc540449ffb2136a10a92554ac01d887590cbb9`.
- Сервіси: KDE Plasma, SDDM із автологіном `wsm`/`plasma`, `elogind`,
  NetworkManager, WPA supplicant, serial console `ttyS0,115200`.
- Власні інструменти: `wsm-hwcheck`, `wsm-install` і launcher
  `wsm-install-live` (read-only preflight + diagnostic-only план) та
  `.desktop`-запис `WSM Installer (preflight)`.

## Відтворення

У середовищі з Guix (у цьому проєкті — ізольований профіль `guix-m1`):

```sh
guix system image -t uncompressed-iso9660 systems/live-iso.scm
sha256sum "$(readlink result)"
```

## Перевірка, яка вже виконана

- `guix system image -n -t uncompressed-iso9660 systems/live-iso.scm` → `exit=0`.
- Реальний boot у disposable QEMU: `q35,accel=tcg`, 2048 MiB, 2 vCPU,
  `-cdrom ISO`, `-nic none`, serial stdio. Отримано маркери
  `This is the GNU system.  Welcome.` і `wsm-kde login:`; root-вхід показав
  `root@wsm-kde ~#`.
- `screendump` через QEMU monitor: 1280×800 графічний framebuffer із
  Breeze-подібним фоном, а не текстова консоль.
- Копія на Ventoy: `D:\wsm-desktop-kde-20261125.iso`, поруч із початковим
  `omarchy-4.5.0-x86.iso` (його не змінено).

## Чесні обмеження

- `wsm-install-live` не виконує REALIZE/APPLY і не пише на диск; наскрізна
  інсталяція лишається за #112 та контрактом
  [`INSTALLER-HANDOFF.md`](INSTALLER-HANDOFF.md).
- Free-only Guix snapshot не містить монолітного `linux-firmware`; blobs для
  частини GPU/Wi-Fi відсутні. Compatibility-профіль драйверів — окрема робота
  за #171.
- У serial-лозі гостьового ядра є попередження `init[1]: segfault ... in guile`
  на ранньому етапі; система дійшла до логіну, але це потребує окремого
  розслідування перед фінальним релізом.
- **Цей SHA відповідає попередній тестовій конфігурації, не оновленому security fix.**
  Під час тієї перевірки в образі був статичний пароль `wsm`, користувач входив
  до `wheel`, а root увійшов через serial із порожнім паролем. Такий образ не
  можна розповсюджувати. Поточний source lock-ить пароль `wsm`, прибирає
  `wheel` і явно забороняє порожні паролі в Guix `login-service-type`.
  Ці зміни ще потребують нового exact-lock build та QEMU перевірки; старий SHA
  не слід приписувати новому source.
- Channel authentication для попередньої локальної збірки була вимкнена, попри
  наявність `channels.lock.scm`; точна збірка з authenticated lock лишається
  окремим gate за #39.
