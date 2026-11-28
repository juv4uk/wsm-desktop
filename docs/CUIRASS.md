# Cuirass: Guix-native build farm

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **NOT_REGISTERABLE / NOT RUN** — очікує owner-signed WSM channel Phase B
- Target host: окремий Guix build host; Cuirass не входить до WSM desktop/live images
- Файли: [ci/cuirass/specs.scm](../ci/cuirass/specs.scm), [ci/cuirass/images.scm](../ci/cuirass/images.scm), [ci/cuirass/service.scm](../ci/cuirass/service.scm)
- Канонічна задача: [#691](https://github.com/juv4uk/wsm-desktop/issues/691)

## Межа відповідальності

Cuirass — Guix-native evaluator/build farm. Він не замінює GitHub Actions і не створює сам по собі release evidence.

| Перевірка | Власник |
| --- | --- |
| Scheme/source checks та швидкі policy tests | GitHub Actions |
| Guix derivation evaluation/build на pinned inputs | Cuirass (після Phase B) і Guix evaluation workflow |
| BIOS/UEFI boot, serial crash gate, installer guest execution | тільки GitHub Actions + QEMU |
| H170/GP107 physical acceptance | owner-approved native hardware test |
| Substitute publication | окремий Guix publish deployment; зараз вимкнено |

Зелений Cuirass build означає лише, що derivation/closure зібрався. Він не означає, що ISO завантажується, що інсталятор працює або що можна публікувати RC.

## Що Cuirass не доводить

- Cuirass **не завантажує образ**: його job закінчується на derivation/closure build, без BIOS або UEFI boot.
- Cuirass **не перевіряє інсталятор**: у job немає QEMU guest чи маркера `WSM_INSTALLER_OK`.
- Він не створює serial crash evidence і не замінює #717, #700 чи release readiness checker.

## Чому зараз не можна реєструвати jobset

WSM channel **не автентифікований**: немає owner-signed introduction, .guix-authorizations та перевіреного public keyring. Тому specs.scm навмисно містить OWNER_SIGNED_WSM_COMMIT_REQUIRED, а не рухому гілку main.

До завершення Phase B:
- не запускати cuirass register із цими specs;
- не замінювати placeholder вигаданим commit/fingerprint;
- не використовувати --disable-authentication;
- не запускати broad channel job;
- не вмикати guix publish, remote workers або публічні substitutes.

Після Phase B власник має замінити placeholder на exact authorized WSM commit, перевірити нормальний authenticated guix time-machine consumer і повторно пройти allowlist/license review #367. Лише тоді можна реєструвати окремий Free jobset. Compatibility має окремий lock, окрему policy та окрему чергу після власних acceptance/legal gates.

## Реалізація custom image job

Файл ci/cuirass/images.scm відповідає Scheme module (ci cuirass images) — module namespace та фізичний шлях мають збігатися. Він використовує API pinned Guix commit 4e5195be:
- arguments->systems та image->job з (gnu ci);
- image-with-os та iso9660-image з (gnu system image);
- image->job передає image record у system-image та повертає Cuirass job.

Немає operating-system-image або довільного #:target API. image->job — штатний helper Guix для Cuirass image jobs. Pinned Guix smoke викликає custom callback і перевіряє metadata згенерованого ISO derivation, а також створює service object; це не будує ISO, не реєструє jobset і не запускає Cuirass instance. Фактичний Cuirass instance/build тут ще не запускався.

ci/cuirass/service.scm — helper для окремої host OS configuration. Він приймає вже підготовлений specifications gexp, використовує (gnu services cuirass) і не вигадує file path у неіснуючому system profile. Він не підключається до WSM live image.

## Substitute і release publication

Cuirass локально планує jobs та записує результати у свій build store/database. Це **не** означає, що substitutes автоматично доступні іншим. Для цього потрібен окремий guix publish service, trusted signing key, substitute URL/fingerprint distribution, store retention та security review.

Публічне substitute serving не дозволене цим PR. Воно чекає:
1. owner-approved key custody та substitute trust model;
2. #367 license/package clearance;
3. окрему host/retention/monitoring policy;
4. окреме рішення власника про публікацію.

## Ресурси та межі

- Перший host: один локальний worker; remote workers не вмикати до вимірювання черги та ресурсів.
- Store quota, log retention, build timeout та database backup мають бути налаштовані на disposable Guix host до запуску.
- Cuirass не виконує QEMU acceptance, не торкається owner H170 disks/BIOS і не викликає GPU workloads.
- #711 Guile serial segfault, #700 guest tool closure та BIOS/UEFI acceptance залишаються окремими release gates.

## Поточний стан

**Інстанс не запускався.** У цьому середовищі немає підключеного Guix/PostgreSQL build host; ця зміна виправляє source/API контракт і додає fail-closed guards, але не стверджує, що Cuirass зареєстровано або що образ зібраний ним.
