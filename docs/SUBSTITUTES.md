# Пакети Guix: перша контрольована публікація WSM

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Канонічне рішення — [ADR 0010](decisions/0010-publish-own-packages.md), реєстр — [docs/DECISIONS.md](DECISIONS.md), канонічне завдання — [#367](https://github.com/juv4uk/wsm-desktop/issues/367).

## Дозволений контур

Згідно з ADR 0010 перша публікація обмежена власним пакетом каналу WSM:

- пакет: wsm-tools;
- збірка: guix time-machine -C channels.lock.scm -- pack --format=tarball --no-grafts -L . wsm-tools;
- trigger: лише ручний workflow_dispatch з main;
- вихід: нова чернетка GitHub Release з pack tarball, pinned lock, описом каналу, package definition, provenance і SHA256;
- після створення workflow перевіряє, що реліз лишився Draft, завантажує assets назад, перевіряє SHA256 і читає tarball;
- Guix signing key, guix archive --export, HTTP substitute cache та GitHub Pages не використовуються.

guix pack формує tarball зі вказаними binaries та їхніми залежностями. Це application bundle, а не Guix substitute cache чи окремі NAR assets. Див. офіційний GNU Guix Reference Manual, розділ «Invoking guix pack».

## Межі

ADR 0010 не дозволяє розширювати перший пакетний реліз на сторонні packages:

- linux-libre, Mesa та інші upstream packages не розповсюджуються цим WSM-owned release;
- Nonguix, proprietary NVIDIA driver, GP107 FECS/GPCCS firmware, Intel nonfree firmware і microcode не включаються;
- linux-wsm-gp107 не переноситься з system definition до каналу цим PR;
- drivers/profiles/h170-free-packages.scm із 11 upstream roots залишається артефактом hardware evaluation/build research, але не є списком пакетів для цього distribution lane;
- package build не є підтвердженням physical H170 boot, Intel i915 binding, GP107 Nouveau KMS, 3D/compute або повної hardware support.

У власному wsm-tools package metadata досі є окремі джерельні питання, описані ADR 0010 / #367. Ця публікація використовує лише дозвіл власника на розповсюдження власного коду; вона не переписує effective license metadata і не змінює ліцензію інших компонентів.

## Substitute cache

.github/workflows/substitutes.yml лишається вимкненим явним if: false, відповідно до ADR 0010. Він не запускається автоматично й не генерує чи зберігає ключ. Окреме рішення власника потрібне, перш ніж створювати довготривалий signing identity або відкривати substitute endpoint.

Попередній run [46115320185](https://github.com/juv4uk/wsm-desktop/actions/runs/46115320185) зупинився на відсутніх GUIX_SIGNING_KEY і GUIX_SIGNING_PUBLIC_KEY до оцінювання пакетів. Цей run не доводить успіх чи помилку Guix build. Після ADR цей workflow навмисно залишається вимкненим.

## Як виконати першу публікацію

Після злиття відповідних змін:

1. Відкрити GitHub Actions → WSM package archives.
2. Запустити Run workflow на main.
3. Дочекатися завершення guix pack, створення Draft Release та read-back перевірки SHA256SUMS.

Workflow не має тегового чи push-trigger. Навіть після успішного завершення реліз лишається чернеткою й не роздається публічно, доки власник окремо не опублікує його.
