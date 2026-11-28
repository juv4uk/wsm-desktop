# Cuirass: Guix-native build automation

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **NOT_REGISTERABLE / NOT_RUN** — потрібні owner-signed WSM channel Phase B та окремий Guix build host
- Guix input: pinned commit з `channels.lock.scm`
- WSM input: навмисний placeholder `OWNER_SIGNED_WSM_COMMIT_REQUIRED`, не рухома гілка
- Специфікація: один custom Minimal Live ISO job; без broad channel build і без package job до рішення #367

## Ролі перевірок

| Перевірка | Що доводить |
| --- | --- |
| GitHub Actions source/policy checks | Синтаксис, policy та регресійні умови |
| Pinned Guix evaluation | Завантаження модуля, створення Cuirass service та lowering ISO до derivation |
| Реальний Cuirass instance/job | Реєстрацію jobset і збірку derivation на окремому Guix host |
| QEMU release workflow | BIOS/UEFI boot і запуск installer guest |
| Native H170 evidence | Фактичну сумісність GA-H170-Gaming 3 / GP107 |

Pinned Guix evaluation **не будує ISO**. Реальний Cuirass derivation build не завантажує образ у BIOS/UEFI й не перевіряє інсталятор. Для цього потрібні окремі QEMU докази, зокрема serial crash gate та `WSM_INSTALLER_OK`.

## Межа довіри: WSM Phase B

Production jobset не можна реєструвати, доки власник не завершив і не перевірив:

1. WSM `.guix-authorizations` та owner-signed introduction/history;
2. public keyring і звичайний `guix git authenticate` consumer;
3. точний immutable WSM source commit у release lock.

У специфікації використаний завідомо непридатний commit placeholder `OWNER_SIGNED_WSM_COMMIT_REQUIRED`. Це навмисний fail-closed стан, а не пропущене поле. Не замінювати його вигаданим SHA/fingerprint, не використовувати `--disable-authentication` і не реєструвати jobset до завершення Phase B.

## Межа ліцензування та substitutes

У Cuirass лишається тільки один custom ISO job. Broad `(build '(channels wsm))` та `wsm-tools` package job вимкнені, доки #367 не вирішить суперечність між package metadata та repository license declarations.

Cuirass local store/database не є автоматичним substitute server. Не налаштовувати `guix publish`, не розповсюджувати WSM substitutes та не створювати publish signing keys без окремого owner-approved license, trust, retention і network design. Issue #367 і майбутнє substitute serving — незалежні рішення.

## Host service

`ci/cuirass/service.scm` — фрагмент для окремого Guix build host, не компонент desktop/live image. Він використовує `(gnu services cuirass)`, наявні поля pinned `cuirass-configuration`, loopback `localhost:8081` та specs file як store input.

Важливо: у pinned Guix `local-file` резолвить відносний шлях від поточного робочого каталогу (`getcwd`), а не від розташування Scheme source. Тому сервісний фрагмент треба оцінювати з кореня checkout; в ньому використаний явний шлях `ci/cuirass/specs.scm`.

UI Cuirass не має вбудованої автентифікації. Не відкривати порт 8081 у публічну мережу; віддалений доступ потребуватиме окремого автентифікованого reverse proxy/TLS та мережевих ACL.

## Що зараз не виконано

- Cuirass instance та PostgreSQL не запускалися.
- Jobset не реєструвався.
- Жоден Cuirass job або ISO derivation не був зібраний.
- WSM Phase B не завершена.
- BIOS/UEFI QEMU acceptance і #711 Guile crash gate лишаються окремими.
- H170/GP107 native Linux acceptance не проводився.

Зелений source/pinned-Guix workflow не змінює ці статуси. До отримання реального runtime evidence стан лишається **NOT_RUN**.
