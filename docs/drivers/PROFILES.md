# Профілі драйверів і firmware

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

## Призначення

Каталог містить окремі машиночитані профілі для конкретної reference-машини H170-Gaming 3. Це реєстр доказів і кандидатів, а не список гарантій сумісності й не автоматичний пакет для встановлення.

- drivers/profiles/h170-free.json — базовий вільний профіль.
- drivers/profiles/h170-compatibility.json — окремий opt-in запис кандидата NVIDIA 580.x для Pascal. Він не вмикає й не розповсюджує драйвер.
- drivers/schema/profile.schema.json — JSON Schema Draft 2020-12.

## Рівні доказів

Поля навмисно розділяють етапи, які не можна зводити до одного прапорця:

1. package_resolution — чи знайдено пакет у конкретному pinned Guix channel.
2. kernel_config — чи драйвер вбудований або доступний як модуль у конкретному ядрі.
3. live_rootfs, initrd, installed_rootfs — чи є потрібні файли саме на відповідному етапі завантаження/роботи.
4. runtime_binding і runtime_load — чи драйвер реально прив'язався до пристрою та чи завантажив потрібне firmware.
5. functional_validation — окремий тест функції пристрою в названому середовищі.

not-assessed означає, що перевірки ще не було. unknown означає, що наявних даних недостатньо. Ні те, ні інше не означає ані успіх, ані помилку.

## Початковий H170 target

Фізичний профіль із juv4uk/wsm-os/docs/OWNER-HARDWARE-PROFILE.md, повторно перевірений 2026-09-02, описує Gigabyte H170-Gaming 3 / Intel Core i5-6400 / Intel HD Graphics 530 / NVIDIA GTX 1050 Ti Pascal / Killer E2200 / Kingston NVMe / Samsung SATA / HDA audio.

Профіль джерела є Windows-observed. Для NVIDIA GeForce GTX 1050 Ti Windows PnP зафіксував vendor:device ID `10de:1c82` (`VEN_10DE DEV_1C82`, subsystem `SUBSYS_33511462`); це є доказом ідентичності пристрою у Windows, але не Linux driver binding. BDF `00000000:01:00.0` — лише адреса пристрою на шині й не є PCI ID. Для інших адаптерів PCI IDs не вигадуються та залишаються порожніми до read-only Linux inventory на фізичній машині. Wi-Fi та Bluetooth не підтверджені й залишаються `unobserved`. Windows identity сама по собі не доводить наявність Linux-модуля, firmware у rootfs/initrd, runtime binding чи функціональність.

## Guix provenance

Обидва JSON профілі прив'язані до commit 4e5195be20d9b124df8a8bb69213412236e4668e з channels.lock.scm. У коментарі зазначено authenticated pull, але побудову пакунків/образу на цьому commit ще не виконано. Це не evidence, що модуль існує в ядрі, пакет присутній у rootfs або firmware включено до initrd.


## Оновлені upstream-орієнтири для GTX 1050 Ti (2026-11-26)

Ці довідки уточнюють покоління-кандидати, але не підвищують жоден runtime/build статус у маніфестах:

- **Вільний шлях Nouveau/NVK:** актуальна [документація Mesa NVK](https://docs.mesa3d.org/drivers/nvk.html) вказує Kepler і новіші покоління, Vulkan 1.4 для офіційно підтриманих GPU та мінімальне ядро Linux 6.6. Документація окремо попереджає, що developer-only override може відкрити навіть погано перевірені або зламані GPU. Це не доводить роботу PCI ID `10de:1c82`, Guix-пакета чи KDE acceleration на H170.

- **Compatibility-шлях NVIDIA:** NVIDIA визначає Linux 580.x як останню Unix-гілку для Pascal ([строки підтримки](https://nvidia.custhelp.com/app/answers/detail/a_id/3142/kw/windows%20supported/related/1)). Для Pascal потрібен proprietary kernel-module flavor; відкриті NVIDIA kernel modules доступні лише для Turing і новіших поколінь ([офіційний посібник](https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/610/kernel-modules.html)). Не підміняти цю залежність open-module пакетом.

Це лише upstream references. У профілях навмисно залишаються `package_resolution: not-assessed`, `kernel_config: not-assessed`, `runtime_binding: unknown`, `functional_validation: not-run` та невизначені license/redistribution. Наступний доказ — точний Guix package/closure і ABI на зафіксованому channel; після цього окремо потрібні image/rootfs/initrd inspection та фактичний тест. Не використовувати developer override як production acceptance.

## Валідація

Запустити:

    python3 tests/test_driver_profiles.py

До інтеграції у Live ISO потрібно заповнити кожне поле реальним результатом pinned package query/build, перевірити rootfs/initrd окремо та зберегти точні логи/версії. Для функціонального статусу потрібен окремий QEMU або дозволений physical test; QEMU/WSL не доводять binding на фізичному H170.

## Межі безпеки

Профілі не виконують firmware update, не завантажують модулі, не монтують/форматують диски та не змінюють EFI. `profile_class: free` і `enabled_by_default: true` описують клас та політику ввімкнення, а не підтверджують Free-сумісність кожного пакета. Для неперевірених кандидатів `source_license` лишається `unknown`, а `package_resolution` — `not-assessed`, доки пакет не перевірено на точній ревізії з `channels.lock.scm` і не завершено окремий license review. Free profile не містить Nonguix або proprietary components. Compatibility profile вимкнений за замовчуванням; ліцензія, ABI, походження та право розповсюдження NVIDIA package залишаються unknown до окремого review.

## Наявний system-level Compatibility профіль

`systems/compatibility.scm` тепер існує в `main` як окремий opt-in рецепт Nonguix/NVIDIA `nvda-580`. Це не робить H170 compatibility manifest buildable: наявний `channels.lock.scm` фіксує лише офіційний Guix, а recipe потребує `(nonguix transformations)` і `(nongnu packages ...)`. Поки немає окремого authenticated `channels.compatibility.lock.scm` з точними Guix + Nonguix commits та введенням ключів, статус package resolution/build/redistribution у H170 compatibility лишається `not-assessed`/`unknown`. Free profile та основний `systems/live.scm` не повинні імпортувати Compatibility чи Nonguix.
