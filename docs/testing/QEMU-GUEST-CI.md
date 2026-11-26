# QEMU acceptance у GitHub Actions

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **єдиний CI workflow, окремий обов'язковий job**
- Workflow: `.github/workflows/ci.yml`
- Job: `qemu-acceptance`
- Документи суміжних рівнів: [HWCHECK-QEMU-GUEST.md](HWCHECK-QEMU-GUEST.md), [../INSTALLER-QEMU-HARNESS.md](../INSTALLER-QEMU-HARNESS.md)

## Навіщо це окремо від швидких тестів

Job `checks` перевіряє Python, документацію, окремі Free/Compatibility channel locks і product-aware release gate; `incomplete` (exit 2) не видається за PASS. Він не доводить, що QEMU справді запустив ядро або що наш collector виконався всередині гостьової Linux-системи.

Тому один workflow має окремий `qemu-acceptance` із межею 30 хвилин. Він запускається на кожен push у `main`, кожен pull request і ручний `workflow_dispatch`; path filters навмисно не використовуються, щоб обов'язкова перевірка не зникала зі статусів через новий шлях у репозиторії.

## Рівні перевірки

1. **Generic Linux guest.** `scripts/ci_qemu_guest_smoke.sh` завантажує ядро runner-а під QEMU TCG, без диска й мережі; гість мусить вивести `WSM_QEMU_GUEST_INIT_OK`.
2. **WSM hardware collector.** `scripts/ci_qemu_hwcheck_guest.py` запускає реальний `python -m wsm_hwcheck` у гостьовому ядрі. Гість читає власні read-only `/proc` і `/sys`, передає звіт через serial; host перевіряє SHA-пінований CPython runtime, bounded transport та JSON Schema.
3. **CXL sysfs guest.** `scripts/ci_cxl_qemu_guest.py` копіює тільки dependency closure модулів вибраного runner kernel та перевіряє enumeration віртуального CXL Type 3 пристрою. Host modules не завантажуються, host sysfs не змінюється.
4. **Synthetic ISO через WSM harness.** Job будує тимчасовий GRUB/BusyBox ISO та запускає його через `scripts/qemu_boot_smoke.py`. Очікується `WSM_QEMU_HARNESS_ISO_BOOT_OK`; harness створює лише одноразовий qcow2 і перевіряє isolation flags.
5. **Policy tests.** Перевіряються QEMU argument builder, bounded serial/stderr capture, CXL module-copy limits, installer capability matrix та contract самого workflow.

## Ізоляція

- Тільки GitHub-hosted `ubuntu-24.04` runner та QEMU TCG; KVM і host CPU passthrough не вмикаються.
- Усі QEMU guests без мережі (`-nic none`).
- Немає host block-device, USB/GPU passthrough, shared folders або EFI variable store.
- Writable qcow2, initramfs і synthetic ISO живуть у тимчасовому runner-каталозі.
- Немає фізичного диска, firmware flash, Guix APPLY або автоматичного оновлення драйверів.
- Workflow має лише `contents: read`, не використовує repository secrets.
- Кожен процес має власний wall-clock timeout; job обмежено 30 хвилинами.

## Ручна Guix evaluation

Job `guix` запускається тільки через `workflow_dispatch`. Він оцінює Free system files і home environment через pinned `channels.lock.scm`.

Далі окремо перевіряються `systems/compatibility.scm` та `systems/live-compat.scm` через `channels/compatibility.lock.scm`. Якщо окремого lock немає, job повертає явний `NOT_CONFIGURED` і exit code 2. Він не підміняє цей стан успіхом Free lock або пропущеним кроком. Канал має пройти звичайну authentication перевірку Guix; `--disable-authentication` не використовується.

## Єдина точка агрегації

Job `acceptance-gates` має `if: always()` та перевіряє результати `checks`, `qemu-acceptance` і, для ручного запуску, `guix`. На звичайному push/PR Guix відображається як `not-run`, бо він manual-only. Невдалий, скасований або пропущений QEMU job не перетворюється на PASS.

## Межі висновку

- Generic guest boot доводить запуск ядра й init, а не WSM ISO.
- HWCHECK guest доводить роботу collector-а на віртуальних `/proc` і `/sys`, а не фізичне виявлення всіх пристроїв.
- CXL guest доводить лише синтетичне QEMU enumeration; це не фізичний CXL hardware test.
- Synthetic ISO доводить роботу QEMU harness, а не збірку чи завантаження Guix-generated WSM image.
- Фізична сумісність GTX 1050 Ti, Wi-Fi, audio, storage або реального монітора залишається окремим owner-hardware acceptance.

Усі рівні мають власний маркер і bounded output. Відсутність runtime evidence — `not-run`, не `pass` і не `fail`.
