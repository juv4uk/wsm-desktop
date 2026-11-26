# Запуск WSM hardware checker та installer preflight у гостьовій Linux-системі QEMU

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **ручна QEMU runtime-перевірка; не входить у hosted CI**
- Пов'язано: #3 (hardware preflight), #13 (власний installer CLI), #14 (QEMU integration), #16 (hardware evidence), #64 (bounded serial/stderr capture), #66
- Runner: `scripts/ci_qemu_hwcheck_guest.py`
- Host dependencies: `qemu-system-x86_64`, `busybox-static`, `cpio`, `kmod` (`modprobe`), `ldd`, `gzip`, `sudo`, `mknod`, `timeout`, `zstd`, `xz`.
- Підготовка та запуск:

  ```sh
  python3.11 -m pip install -r requirements-dev.txt
  PYTHON=python3.11 make qemu-acceptance-manual
  ```

## Ланцюг перевірки

Linux host готує тимчасовий initramfs із runner kernel, BusyBox та pinned CPython runtime. Усередині QEMU-гостя запускається справжній `wsm_hwcheck`: він читає власні read-only `/sys` і `/proc` та записує Hardware Evidence Report у єдиний шлях `WSM_HWCHECK_REPORT`.

Після collector-а той самий гість виконує власний `wsm-install --preflight --report <той самий файл> --backend guix --dry-run --quiet`. Жодного synthetic report або host `/sys` замість guest evidence не підставляється. CLI smoke перевіряє, що план залишається:

- `plan_status=diagnostic-only`;
- `plan_readiness.confirmable=false`;
- `execution.dry_run=true`;
- `mutations_authorized=false`;
- `backend_invoked=false`;
- `disk_access_performed=false`.

Звіт прив'язується до точних raw bytes через SHA-256; canonical plan має окремий `plan_sha256`. Host приймає рівно один bounded serial marker із фіксованим набором полів.

## Runtime Python та ABI

Guest використовує незмінний upstream `python-build-standalone` tag `20261123`:

- CPython 3.11.18, target `x86_64-unknown-linux-gnu`;
- archive `install_only_stripped`;
- SHA-256: `75b92c55bc6a5f58fe4d08fc5261c983b2b17930192d62946fe7c9cf6fd66316`.

Для копіювання native validator wheels host також має працювати під CPython 3.11 з ABI `cpython-311`. Запускайте повну перевірку явно як `PYTHON=python3.11 make qemu-acceptance-manual`. Runner fail-closed відмовляється копіювати wheels з іншою ABI — зокрема CPython 3.12 extension не можна імпортувати в Python 3.11 guest. `jsonschema[format]` обмежено версією 4.26.0; повний allowlist distributions формується на host і копіюється до тимчасового initramfs. Усередині гостя немає pip, package manager або мережі.

GNU/Linux runtime не називається static. Скрипт перевіряє ELF-залежності через `ldd`, відмовляється від unresolved libraries та копіює лише знайдені зовнішні shared libraries.

## Ізоляція й обмеження

- QEMU TCG, 2 GiB guest RAM, 1 vCPU та bounded wall-clock timeout.
- Гість завантажується з kernel та initramfs; віртуального диска немає.
- `-nic none`; немає host block device, USB/GPU passthrough, shared folders або EFI variable store.
- Python archive обмежено 40 MiB; tar — 50 000 записів і 256 MiB розпакованих файлів; initramfs — 256 MiB; report — 512 KiB; installer plan — 64 KiB.
- Serial і stderr мають фіксовані ліміти; переповнення capture або відсутній/дубльований marker — hard failure.
- CLI блокує `subprocess.run/Popen` та мережеві socket APIs; Guix backend не викликається.

Успіх доводить лише, що QEMU guest collector створив звіт і власний `wsm-install` сформував на ньому read-only, non-confirmable diagnostic plan. Це **не** WSM ISO boot, authenticated Guix channel build, Guix deployment, запис на диск, інсталяція або фізична перевірка H170/GTX 1050 Ti. Для цього потрібен окремий WSM-owned ISO та disposable-disk end-to-end сценарій; цей harness його не замінює.
