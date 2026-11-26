# Вимірювання готовності сесії KDE Plasma

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: реалізовано як collector та Guix Home autostart; runtime на Guix/Plasma ще не перевірено.
- Канонічна задача: [#151 — вимірюваний baseline boot, services і desktop workloads](https://github.com/juv4uk/wsm-desktop/issues/151)
- Артефакт: wsm-desktop-session-readiness/1
- Тест: tests/test_session_readiness.py

## Що саме вимірюється

Команда wsm-session-marker фіксує виконання KDE XDG autostart phase 2. Plasma запускає цю фазу після phase 1 і відновлення програм попередньої сесії. Це контрольна точка для login-to-session-phase-2, але не доказ, що кожна служба, периферія, мережа чи застосунок уже готові.

Маркер не змінює SDDM, compositor, system targets або Shepherd. Він запускається лише у KDE через OnlyShowIn=KDE та X-KDE-autostart-phase=2. Для запуску потрібен Guix Home профіль із systems/home.scm; він додає wsm-tools і файл autostart/wsm-session-readiness.desktop до XDG configuration.

## Джерело часу

Початок сесії читається через фіксований read-only виклик loginctl show-session і властивість TimestampMonotonic інтерфейсу org.freedesktop.login1.Session. На Guix ця функціональність надається elogind. Поточна точка phase 2 береться з CLOCK_MONOTONIC; обидва timestamps мають одну монотонну шкалу в мікросекундах.

login_to_phase2_ms — різниця між цими двома значеннями. Якщо loginctl, session ID чи timestamp відсутні, маркер усе одно записує факт phase 2, але стан артефакту буде partial, а затримка — null. Немає підміни нулем і немає fallback до wall-clock часу.

Upstream:
- [KDE Plasma session startup phases](https://github.com/KDE/plasma-workspace/blob/master/ksmserver/README)
- [elogind loginctl(1)](https://manpages.debian.org/unstable/elogind/loginctl.1.en.html)
- [elogind login1 Session API](https://manpages.debian.org/trixie/elogind/org.freedesktop.login1.5.en.html)
- [XDG Autostart Specification](https://specifications.freedesktop.org/autostart/latest/index.html)

## Приватність і запис

Артефакт записується атомарно в приватний runtime-каталог:

    $XDG_RUNTIME_DIR/wsm/plasma-phase2-<boot-digest>-<phase2-monotonic-us>.json

Каталог WSM має режим 0700, файл — 0600; власник перевіряється, symlink замість runtime directory відхиляється. Тимчасовий файл fsync-иться перед атомарним rename.

У JSON немає сирого session ID, username, hostname, UID, display name, адрес або повного environment. Session ID взагалі не записується і не хешується: він використовується лише для запиту та перевірки відповіді logind. Короткий SHA-256 digest зберігається лише для boot ID. Ім'я файлу використовує boot digest і монотонний timestamp phase 2. Вивід loginctl не зберігається; читаються лише Id та TimestampMonotonic.

## Межі інтерпретації

- Phase 2 означає, що KDE дійшов до цієї фази автозапуску після відновлення сесії. Це не гарантія інтерактивної готовності кожного застосунку або відсутності фонового I/O.
- Час включає інтервал від створення login manager session до phase 2; це не тотожне часу від натискання пароля у SDDM, firmware/bootloader time або холодному старту ядра.
- Значення не порівнюються між різними DE, manager-ами, типами сесії, апаратними класами чи конфігураціями без окремого протоколу.
- Session marker не запускається у hardware preflight, installer або звичайному CI; немає polling, timer, shell, privilege escalation або disk writes.
- CI перевіряє логіку, privacy, схему й безпечний запис. Реальний runtime evidence на Guix + Plasma ще не знятий і не заявляється.

## Перевірка

    make check-session-readiness
    wsm-session-marker --version

Для аналізу локального артефакту відкрийте відповідний файл у приватному runtime-каталозі. Не публікуйте його без потреби: хоча сирі ідентифікатори прибрані, timestamp і session type усе одно описують конкретний локальний запуск.
