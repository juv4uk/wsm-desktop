# Канонічні артефакти рішень WSM

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Цей файл — **реєстр**, а не новий ADR. Він відповідає на питання «який документ і яке завдання є канонічними для цієї теми?». Зміст ADRів і контрактів залишається у своїх файлах.

- Статус: процесна угода, запропонована у [#54](https://github.com/juv4uk/wsm-desktop/issues/54)
- Дата: 2026-11-25

## Правила

1. Перед відкриттям PR, який додає або змінює рішення (ADR, контракт, policy), знайдіть тему в таблиці нижче й залиште коментар у канонічному завданні.
2. Одна тема має **один** канонічний документ і **одне** канонічне завдання. Якщо існує competing artifact, він закривається або явно позначається як `superseded` з посиланням на канонічний шлях.
3. Кожен ADR мусить містити канонічне завдання, статус (`proposed`, `accepted`, `superseded`) і посилання на документи, які він переглядає.
4. Докази, звіти й тести не є окремими рішеннями: вони додаються до вже канонічної теми, а не породжують новий ADR.
5. Web-агент і локальний агент узгоджують owner-а перед створенням другого документа на будь-яку тему з таблиці.

## Реєстр

| Тема | Канонічне завдання | Канонічний документ / PR | Owner | Статус | Superseded / примітка |
| --- | --- | --- | --- | --- | --- |
| Перший системний backend WSM | [#2](https://github.com/juv4uk/wsm-desktop/issues/2) | [ADR 0004](decisions/0004-nix-guix-backend-strategy.md) | architecture / обидва агенти | `accepted` — GNU Guix перший backend; Nix відкладено | Nix/NixOS не відкинуто, але не входить у перший підтримуваний шлях. Автентифікований channel lock і відтворюваність лишаються окремою задачею [#39](https://github.com/juv4uk/wsm-desktop/issues/39). |
| Перевірка мінімальної Guix System у VM | [#1](https://github.com/juv4uk/wsm-desktop/issues/1), gate [#55](https://github.com/juv4uk/wsm-desktop/issues/55) | [evidence comment](https://github.com/juv4uk/wsm-desktop/issues/1#issuecomment-7172142987), PR [#65](https://github.com/juv4uk/wsm-desktop/pull/65) | local agent | verified | Build без реального boot не є доказом; див. #55. |
| Вибір installer frontend | [#10](https://github.com/juv4uk/wsm-desktop/issues/10), evidence [#11](https://github.com/juv4uk/wsm-desktop/issues/11) | PR [#100](https://github.com/juv4uk/wsm-desktop/pull/100) (`docs/decisions/0006-hardware-first-installer-frontend.md` після злиття) | local agent | `proposed`, не ратифіковано | Вибір Calamares з [ADR 0002](decisions/0002-calamares-as-installer.md) deprioritized; ADR 0006 явно переглядає його в цій частині. |
| Preflight → plan → backend handoff | [#12](https://github.com/juv4uk/wsm-desktop/issues/12) | [docs/INSTALLER-HANDOFF.md](INSTALLER-HANDOFF.md), PR [#17](https://github.com/juv4uk/wsm-desktop/pull/17) | web agent | `proposed / design-only` | PR [#15](https://github.com/juv4uk/wsm-desktop/pull/15) закрито як superseded; PR [#44](https://github.com/juv4uk/wsm-desktop/pull/44) — дублікат, закрито. |
| Схема звіту апаратних доказів | [#5](https://github.com/juv4uk/wsm-desktop/issues/5) | [docs/hardware/REPORT-FORMAT.md](hardware/REPORT-FORMAT.md), [schema](../schemas/hardware-report.schema.json) | web agent | versioned v1.0.0, issue відкрито | Розширення топології належить до #18/#42, а не до нового ADR. |
| Read-only hardware collector | [#6](https://github.com/juv4uk/wsm-desktop/issues/6) | [docs/hardware/HWCHECK.md](hardware/HWCHECK.md), `wsm-hwcheck` | web agent | prototype v0.1.0, issue відкрито | Frontend споживає звіт, але не змінює collector. |
| Аудит upstream hardware tooling | [#4](https://github.com/juv4uk/wsm-desktop/issues/4) | [UPSTREAM-TOOLING.md](hardware/UPSTREAM-TOOLING.md), [addendum](hardware/UPSTREAM-TOOLING-ADDENDUM-2026-11-25.md) | web agent | research, issue відкрито | Докази доступності пакетів додаються коментарем до #4, не новим документом. |
| Топологія пристроїв та інтерфейсів | [#18](https://github.com/juv4uk/wsm-desktop/issues/18), [#42](https://github.com/juv4uk/wsm-desktop/issues/42) | [docs/hardware/TOPOLOGY-RELATIONSHIPS.md](hardware/TOPOLOGY-RELATIONSHIPS.md) | web agent | proposed / документ злито | Зв'язки, яких немає у схемі, лишаються `unknown`. |
| Свіжість live-сесії | [#23](https://github.com/juv4uk/wsm-desktop/issues/23) | обговорення #23, `wsm_install/freshness.py` | web agent | unresolved | `collected_at` + збіг kernel/arch не доводять ту саму boot-сесію. |
| Calamares feasibility | [#2](https://github.com/juv4uk/wsm-desktop/issues/2), [#10](https://github.com/juv4uk/wsm-desktop/issues/10) | [docs/CALAMARES-FEASIBILITY.md](CALAMARES-FEASIBILITY.md), [ADR 0002](decisions/0002-calamares-as-installer.md) | local agent | assessment / deprioritized | Не відкривати новий ADR лише для переоцінки Calamares; оновлювати цю тему. |
| UEFI pre-boot evidence | [#92](https://github.com/juv4uk/wsm-desktop/issues/92) | [UEFI pre-boot audit](hardware/UEFI-PREBOOT-PROBE-AUDIT.md), PR [#102](https://github.com/juv4uk/wsm-desktop/pull/102) | web agent | audit merged; provider not implemented | Наявний probe з `wsm-os` не переносити як є; ліцензійна межа, окремий evidence envelope та OVMF fixture ще потребують роботи. |
| Синтетична CXL topology evidence | [#94](https://github.com/juv4uk/wsm-desktop/issues/94), related [#18](https://github.com/juv4uk/wsm-desktop/issues/18) | [CXL synthetic topology](testing/CXL-SYNTHETIC-TOPOLOGY.md) | both agents | feasibility / guest test in progress | QEMU enumeration, `cxl_test` та synthetic sysfs fixtures — різні рівні доказу; не є physical CXL compatibility. |
| Канонічність документів | [#54](https://github.com/juv4uk/wsm-desktop/issues/54) | цей файл | local agent | proposed | Додати topic рядок тут замість нового процесного ADR. |

## Що не є темою для нового рядка

- черговий QEMU-запуск або CI-експеримент;
- оновлення версії пакета чи каналу всередині вже канонічної теми;
- виправлення помилки в конфігурації (`#1` / PR #65 — приклад);
- коментар із доказом, який належить до існуючого завдання.

Такі зміни додаються до відповідного issue/PR і не створюють нову точку істини.
