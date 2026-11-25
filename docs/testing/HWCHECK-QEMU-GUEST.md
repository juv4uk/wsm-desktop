# Запуск WSM hardware checker та installer preflight у гостьовій Linux-системі QEMU

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Статус: **CI experiment**
- Пов'язано: #3 (hardware preflight), #13 (installer CLI prototype), #14 (QEMU-only integration), #16 (driver/runtime firmware evidence), #64 (bounded serial/stderr capture), #66
- Runner: `scripts/ci_qemu_hwcheck_guest.py`
- Workflow: `.github/workflows/hwcheck-qemu-guest.yml`

## Що саме перевіряється

GitHub-hosted Ubuntu runner готує тимчасовий initramfs із runner kernel, BusyBox та CPython runtime. Усередині QEMU-гостя виконується реальний код `python -m wsm_hwcheck`. Гість читає власні `/sys` і `/proc`, формує Hardware Evidence Report v1.0.0 та передає стислий звіт через serial. Host runner розпаковує payload і перевіряє його офіційною JSON Schema.

Після collector-а гість окремо запускає справжній `python -m wsm_install --preflight --report ... --backend guix --dry-run --quiet` на синтетичному `desktop-observed.json` fixture з цього repository commit. Це **не** план для фактичного guest hardware: fixture навмисно використовується для перевірки стабільного CLI contract і формування diagnostic-only результату. Гість перевіряє schema, backend alias, canonical plan digest та всі non-mutating execution flags.

Для guest CLI smoke в initramfs додається лише runtime closure `jsonschema[format]`, уже встановлений host workflow з `requirements-dev.txt`; базова версія `jsonschema` фіксується на 4.26.0. Список потрібних distributions явний, їхні фактичні версії друкуються в CI log, а ELF dependencies скануються через `ldd` і копіюються до тимчасового rootfs. У гості немає pip, package manager або мережі — нічого не завантажується зсередини VM.

Під час CLI smoke блокуються `subprocess.run`, `subprocess.Popen`, `socket.socket` і `socket.create_connection`. Очікуваний результат:
- `plan_status=diagnostic-only`;
- `plan_readiness.confirmable=false`;
- `execution.dry_run=true`;
- `mutations_authorized=false`;
- `backend_invoked=false`;
- `disk_access_performed=false`;
- report digest і plan digest відповідають точним байтам та canonical JSON.

Це доводить, що сам CLI у guest може сформувати безпечний dry-run plan на синтетичному report. Це **не** Guix/Nix backend invocation, disk preparation, install або фактична оцінка сумісності fixture-пристроїв.

## Runtime CPython

Для цього CI experiment використовується незмінний upstream release python-build-standalone tag 20261123:
- CPython 3.11.18, target x86_64-unknown-linux-gnu;
- archive install_only_stripped;
- SHA-256: `75b92c55bc6a5f58fe4d08fc5261c983b2b17930192d62946fe7c9cf6fd66316`;
- завантаження відбувається лише у host runner, з перевіркою digest перед розпакуванням.

GNU/Linux build не називається static. Runner перевіряє ELF-об'єкти у pinned runtime та гостьових validator wheels через `ldd`, відмовляється від unresolved libraries та копіює лише виявлені зовнішні shared-library dependencies. Host `/lib` цілком не копіюється. Python runtime та validator packages не додаються до WSM Guix/Nix closure або production image у межах цього experiment.

## Межі ізоляції

- QEMU TCG, 2 GiB guest RAM, 1 vCPU, обмежений wall-clock timeout.
- Гість завантажується з `-kernel` та initramfs; віртуального диска або CD-ROM немає.
- `-nic none`; немає host block device, USB/GPU passthrough, shared folders або EFI variable store.
- Python archive завантажується host runner до створення guest; гість не має мережевого інтерфейсу.
- Завантаження CPython обмежено 40 MiB; tar — 50 000 записів і 256 MiB розпакованих файлів; initramfs — 256 MiB; JSON-звіт — 512 KiB; installer plan — 64 KiB.
- Serial і stderr читаються через спільний bounded QEMU reader (1 MiB serial, 256 KiB stderr); зберігаються лише обмежені хвости. Переповнення capture — hard failure, частковий звіт не приймається.
- Hardware report та installer CLI запускаються в одному guest Python runtime. CLI schema validation виконується у гості; collector report повторно валідовується на host.

## Acceptance та інтерпретація

Успіх означає, що справжній guest kernel запустив `/init`, CPython імпортував потрібні модулі, `wsm_hwcheck` прочитав guest `/sys` і `/proc`, згенерував звіт, а host успішно перевірив schema v1.0.0 та privacy flags. Далі `wsm-install` у тому самому guest видав diagnostic-only/non-confirmable план на синтетичному fixture без subprocess/network APIs та без backend/disk flags.

Inventory-only guest не повинен видавати functional test зі статусом passed. Unknown або відсутність functional tests залишаються невизначеністю, а не доказом несумісності чи позитивної працездатності.

Це QEMU guest runtime та CLI contract validation, а не WSM ISO boot, authenticated Guix channel build, Guix/Nix backend execution, інсталяція на диск, physical hardware test або глобальна сертифікація сумісності.
