# Ізольована перевірка wsm-hwcheck усередині QEMU guest

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

Цей workflow запускає фактичний пакет `wsm_hwcheck` із поточного commit усередині
тимчасової Linux-гостьової системи QEMU TCG. Це сильніша перевірка, ніж unit tests
або generic guest-init marker, але вона все ще не є сертифікацією фізичного
обладнання чи завантаженням WSM ISO.

## Як працює перевірка

Перед повним QEMU запуском host виконує `tests/test_qemu_hwcheck_guest.py`:
перевіряє LF/CRLF serial parsing, межі report, shell syntax згенерованого
guest `/init` і відхилення tar path traversal. Ці швидкі тести запускаються
також через `make check-qemu-harness`.


1. Host runner завантажує immutable CPython release `20261123` і перевіряє SHA-256.
2. Скрипт створює тимчасовий initramfs із BusyBox, Python runtime і кодом
   `wsm_hwcheck` з цього checkout.
3. Залежності ELF для GNU/glibc Python визначаються локально через `ldd`;
   у guest rootfs копіюються лише потрібні шляхи бібліотек. Runtime не називається
   static і не копіюється з повного host rootfs.
4. QEMU TCG запускає runner kernel без диска, мережевого адаптера, USB/GPU
   passthrough, EFI variable store або shared folder.
5. Guest монтує `/proc` і `/sys` read-only та виконує
   `python3.11 -S -m wsm_hwcheck --compact`.
6. JSON report повертається через обмежений serial pipe, після чого host перевіряє
   schema v1.0.0, privacy flags і відсутність заборонених identifier keys.

## Закріплений Python runtime

- CPython: `3.11.18`
- Upstream immutable release tag: `20261123`
- Asset:
  `cpython-3.11.18+20261123-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz`
- SHA-256:
  `75b92c55bc6a5f58fe4d08fc5261c983b2b17930192d62946fe7c9cf6fd66316`
- Розмір upstream asset: 30,809,935 bytes.

Це GNU/Linux distribution, яка використовує системний dynamic loader і glibc.
Workflow визначає ELF dependencies на runner через `ldd` і додає їх у guest
initramfs за абсолютними шляхами. Це не fully-static Python build. Після
розпакування архів перевіряється через `tarfile` data filter; розмір і кількість
entries обмежені.

Джерела: [офіційний immutable release](https://github.com/astral-sh/python-build-standalone/releases/tag/20261123),
[archive semantics](https://github.com/astral-sh/python-build-standalone/blob/main/docs/distributions.rst),
[runtime dependencies](https://github.com/astral-sh/python-build-standalone/blob/main/docs/running.rst).

## Межі доказу та ізоляція

- Гість бачить лише QEMU virtual hardware, а не host GPU/NIC/storage/monitor.
- Гість не отримує мережу, фізичні пристрої, host block devices, EFI variables чи
  host filesystem mount.
- `/proc` і `/sys` монтуються read-only; writable `/tmp` знаходиться лише в
  RAM-backed initramfs.
- Serial та stderr захоплюються потоково з жорсткими обмеженнями обсягу; timeout
  завершує QEMU.
- Host перевіряє лише report, не відправляє hardware probe у віддалену базу.
- Firmware state, якого гість не може підтвердити, має лишатися unknown.
- Цей workflow не будує Guix/Nix систему, не запускає installer apply і не
  доводить сумісність WSM ISO чи фізичного ПК.

Тому успіх цього тесту закриває лише runtime/schema integration у generic Linux
guest. Для фізичного hardware reference profile потрібен окремий контрольований
тест на реальному обладнанні.
