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
- Після security-fix зібрано новий hardened ISO: SHA-256 `d1a000f8c465b496565b0f611ae6f65095086a8457c663f212ca5b17073fd7ef`; той самий QEMU-boot markers підтверджено, `Login incorrect` не з'являвся, графічний framebuffer 1280×800 збережено. Це ще не compatibility-збірка з NVIDIA.
- Копія на Ventoy: `D:\wsm-desktop-kde-20261125.iso`, поруч із початковим
  `omarchy-4.5.0-x86.iso` (його не змінено). SHA-256 копії, порахований на
  Windows-боці: `C054C6F7AF5119F96739CDAB4FC540449FFB2136A10A92554AC01D887590CBB9`
  — збігається з вихідним ISO.

## Compatibility-профіль для NVIDIA

Вільний ISO вище містить лише відкритий `nouveau` (`nouveau.ko`, Mesa `nouveau_dri.so`, `libvulkan_nouveau.so`). У ньому **немає** `nvidia.ko`, `/lib/firmware/nvidia/...` або `linux-firmware`; ядро — `linux-libre 7.3.5`. Для вашої `NVIDIA GeForce GTX 1050 Ti` (Pascal `GP107`, `0x1c82`) цього недостатньо для пропрієтарного драйвера.

Дані про залізо — з [`wsm-os/docs/OWNER-HARDWARE-PROFILE.md`](https://github.com/juv4uk/wsm-os/blob/main/docs/OWNER-HARDWARE-PROFILE.md): GTX 1050 Ti 4096 MiB, CUDA capability 6.1 (`sm_61`), PCI `01:00.0`, Windows/NVML драйвер `582.66`.

Тому додано окремий [`systems/live-compat.scm`](../systems/live-compat.scm) із зафіксованими каналами [`channels/compatibility.lock.scm`](../channels/compatibility.lock.scm):

- ядро `linux 7.3.5` (не libre);
- `nvidia-service-type` із гілкою **580.xx** — останньою, яка підтримує Pascal (590+ не розпізнає GTX 10xx);
- `nvidia-module-580`, `nvidia-firmware-580`, `nvidia-settings-580` і `linux-firmware`;
- KDE Plasma, SDDM, NetworkManager/WPA, WSM preflight-інструменти — ті самі, що й у вільному профілі.

Збірка (в ізольованому профілі, побудованому з lock-файлу):

```sh
guix time-machine -C channels/compatibility.lock.scm -- \
  system image -t uncompressed-iso9660 systems/live-compat.scm
```

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
  можна розповсюджувати. Поточний source задає `(password #f)`, прибирає
  `wheel` і явно забороняє порожні паролі в Guix `login-service-type`.
  Ці зміни ще потребують нового exact-lock build та QEMU перевірки; старий SHA
  не слід приписувати новому source.
- SDDM autologin для locked account `wsm` у поточному QEMU ще не
  повторно перевірений після security patch. Перед merge/release окремо
  підтвердити: Plasma session стартує як `wsm`, root на `ttyS0` з порожнім
  паролем отримує відмову, а `sudo -n true` від `wsm` не має привілеїв.
- Channel authentication для попередньої локальної збірки була вимкнена, попри
  наявність `channels.lock.scm`; точна збірка з authenticated lock лишається
  окремим gate за #39.
