# Calamares у WSM

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **обов'язковий графічний frontend цільового універсального Live Installer; реалізація ще preview-only**
- Роль: **третій, графічний режим** поряд із консольним CLI та псевдографічним TUI
- Спільний контракт: docs/INSTALLER.md
- Рішення: ADR 0008 (proposed; потребує узгодження зі продуктовою вимогою в #10)

## Призначення

Calamares — не довідковий експеримент і не необов'язкова заміна TUI. Користувач повинен мати змогу вибрати графічне встановлення через Calamares з Installer Selector основного універсального Live ISO. Консольний CLI, псевдографічний TUI і Calamares мають бути доступними як три окремі способи взаємодії з одним WSM installer backend.

Minimal Live для слабкого обладнання може не містити Qt/Calamares і пропонувати лише CLI/TUI. Воно не є основним універсальним образом і має чесно показувати відсутність графічного режиму.

## Розподіл ролей

| Шар | Хто робить |
| --- | --- |
| Вибір режиму | WSM Installer Selector |
| Мова, локація, клавіатура, графічні сторінки | Calamares |
| Partitioning UI | Calamares із KPMcore, після WSM preflight і з явним вибором цілі |
| Hardware evidence та readiness | WSM: wsm-hwcheck і спільний evidence gate |
| Вибір WSM профілю | WSM, через типізований frontend contract |
| Планування та deployment | Єдиний WSM Guix backend |
| Bootloader і system activation | Guix/WSM backend; без паралельного Calamares bootloader writer |

Calamares є frontend та workflow host-ом. Він не створює окремий системний backend. WSM jobmodules передають спільному backend-у типізовані дані, а не довільний shell text.

## Поточний стан

У репозиторії є заготовка Python jobmodule, але вона preview-only й навмисно не завершується успіхом після dry-run. Немає підтвердженого запуску Calamares у live ISO, повного settings.conf, повного module chain або QML сторінки вибору WSM profile. Це ще належить реалізувати.

## Обов'язкові частини інтеграції

- Pinned Calamares upstream source, signature/hash verification та Guix package recipe із повним dependency closure.
- Qt 6, Python jobmodule API, KPMcore і справжній Calamares partition module.
- settings.conf із визначеним порядком сторінок; відключення конфліктних Calamares users/bootloader jobs.
- WSM preflight step до будь-якого disk plan.
- Графічний вибір Free/Compatibility профілю та відображення hardware evidence.
- Перевірка disk identity, розміру, partition map, EFI mount та firmware mode.
- Явний review/confirmation екран до будь-якого запису.
- WSM Guix deployment jobmodule, який викликає тільки спільний backend.
- Звіт про успіх/помилку та post-install verification.

## Контракт jobmodule

Поки APPLY вимкнено, wsm_deploy має повертати failure tuple навіть після успішного preview. None як Calamares success дозволено тільки після того, як окремо reviewed APPLY справді завершив встановлення та post-install verification. Відсутні докази, неоднозначна ціль, невідповідний розмір, непідтверджена операція або помилка backend-а означають fail-closed.

## Заборони безпеки

- Не використовувати os.system, shell=True або shell-команду з довільного тексту UI.
- Не запускати Calamares bootloader job паралельно з Guix bootloader installation.
- Не мати другого partition/filesystem/system writer поза єдиним backend contract.
- Не зберігати паролі, password hashes, tokens або приватні hardware identifiers у логах.
- Не трактувати preview як установлену систему.

## Acceptance

Calamares вважається реалізованим лише після package build у pinned Guix channel, запуску всередині основного WSM Live ISO, проходження повного UI/job sequence у disposable QEMU disk, реального Guix install і повторного BIOS/UEFI boot установленої системи.