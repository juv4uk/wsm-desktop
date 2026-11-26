# План: повторне використання Guix-артефактів без втрати provenance

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Дата: 2026-11-26
- Статус: **proposed / design-only**; жодного нового cache, signing key або deployment path не ввімкнено
- База перевірки: `main@7edec7e2a7ce3a6664f55b1d8bfbe6b11822b9ad`
- Дотичні рішення: [ADR 0001](../../decisions/0001-guix-as-system-foundation.md), [ADR 0004](../../decisions/0004-nix-guix-backend-strategy.md), [performance evidence](../../PERFORMANCE.md)
- Пов'язані задачі: [#1](https://github.com/juv4uk/wsm-desktop/issues/1), [#39](https://github.com/juv4uk/wsm-desktop/issues/39), [#151](https://github.com/juv4uk/wsm-desktop/issues/151)

## Навіщо це дослідити

Omarchy 4.5 запровадила F1 installer, який розпаковує попередньо зібраний root image і додає пакети конкретної машини поверх нього; upstream повідомляє приблизно про дворазове скорочення часу інсталяції ([офіційний реліз](https://github.com/omacom/omarchy/releases/tag/v4.5.0), [пояснення F1](https://omarchy.org/news/2026/11/omarchy-4-5/)). Це корисний performance pattern, але його не можна механічно перенести в WSM.

Для WSM еквівалентом має бути не довільний tar/rootfs і не другий deployment engine, а **попередньо побудовані результати Guix derivations**, які Guix може перевірено отримати як substitutes. Guix прив'язує substitute до derivation output і відхиляє неавторизовані або некоректно підписані результати; довіра визначається authorized-key ACL, а не самим URL сервера ([Guix Manual — substitutes and authentication](https://guix.gnu.org/manual/devel/en/html_node/Substitutes.html)). Для окремих derivations Guix також має `--rounds` для виявлення невідтворюваних збірок та `guix challenge` для зіставлення незалежних результатів ([Guix Manual — build options](https://guix.gnu.org/manual/devel/en/html_node/Invoking-guix-build.html)).

## Межі, які не можна порушувати

1. **GNU Guix залишається єдиним системним backend першого продуктового шляху.** Не створювати паралельний unpack/apply механізм, який обходить майбутній Guix deploy adapter.
2. **Free та Compatibility лишаються окремими продуктами й lock-файлами.** Не додавати Nonguix чи nonfree firmware до Free closure.
3. **Жодного неперевіреного binary cache.** Не додавати substitute URL, публічний ключ або автоматичний trust-on-first-use. Перед використанням зафіксувати effective substitute URLs і fingerprints ключів у disposable runner; зовнішній WSM cache потребує окремого ADR та ручного authorization.
4. **Не змінювати channel pins у цьому дослідженні.** `channels.lock.scm` — точний input; його оновлення та автентифікація лишаються окремим release gate #39. Не використовувати `--disable-authentication`.
5. **Не замінювати Guix покоління rootfs-архівом.** Майбутній install path має зберігати Guix-native system generations і контрольований rollback.
6. Жодних фізичних дисків у CI/QEMU; жодного запуску `guix system init` на host disk.

## Запропонована модель

### 1. Базові derivations

- Free live image будується лише з `systems/live-iso.scm` та `channels.lock.scm` через наявний `scripts/build_iso.sh` (`guix time-machine -C … -- system image`).
- Для майбутнього installable system closure окремо дослідити derivation від typed Guix system configuration. Не вважати live ISO готовою root filesystem для розгортання на диск.
- Спільну, незалежну від конкретної машини частину тримати у Free base; hardware-specific firmware та Compatibility packages лишати окремими derivations і окремим lock.
- Перший етап — отримання тих самих store outputs із вже авторизованих Guix substitute servers, а не власний mirror.

### 2. Provenance кожного артефакту

Поточний build manifest уже фіксує source commit, profile hash, channel-lock hash, Guix revision/version, канали та SHA-256 файлів. До нього можна додати лише після окремого review:

- system target/architecture та image type;
- exact derivation path і store output path;
- output NAR hash/size та статус: substitute hit або local build;
- effective substitute URLs і fingerprints **вже авторизованих** ключів;
- build log, exit code і QEMU acceptance reference для конкретного артефакту.

SHA-256 ISO доводить цілісність файла відносно маніфесту, але сам по собі не є підписом, доказом походження або доказом boot. Підпис release manifest — окрема дія з явним власником ключа.

### 3. Порівняння продуктивності

До будь-якого performance claim:

1. Зафіксувати точні source SHA, Guix версію, обидва lock inputs, machine/runner resources і стан store.
2. На чистому disposable runner виміряти cold build без локальних store outputs.
3. На тому самому lock повторити build із доступними авторизованими substitutes; записати hit/miss для closure, обсяг завантаження і локальної збірки.
4. Порівняти не лише час `guix system image`, а й повний майбутній install path після його реалізації. Не видавати швидший live-ISO build за швидшу інсталяцію ОС.
5. Для стабільного порівняння — щонайменше п'ять повторів, медіану та розкид; використати вже додані PSI/zram observations із [#375](https://github.com/juv4uk/wsm-desktop/pull/375), але не трактувати system-wide pressure як причинний вплив одного workload.
6. Для вибраних derivations виконати повторну збірку/незалежне порівняння через штатні Guix механізми. Будь-яка різниця блокує публікацію як перевіреного substitute.

Наявність високої загальної доступності substitutes у Guix QA не доводить, що конкретний WSM closure вже є на сервері; availability потрібно міряти для точних store paths і pinned inputs ([Guix QA](https://qa.guix.gnu.org/branch/master), [Bordeaux build farm](https://bordeaux.guix.gnu.org/)).

## Етапи та acceptance gates

| Етап | Результат | Умова переходу |
| --- | --- | --- |
| A. Baseline | Cold build / warm build / substitute hit-rate для Free live image | Точні lock, host resources, логи та п'ять вимірів |
| B. Store provenance | Manifest пов'язує derivation, store output, NAR та source inputs | Перевірені SHA і підпис/authorized key; жодного невідомого trust root |
| C. Independent reproducibility | Другий runner отримує побітово узгоджений output | `guix challenge` або відповідний `--rounds` gate успішний |
| D. QEMU acceptance | Точний опублікований образ завантажується в disposable QEMU/OVMF | Serial marker, exact image digest, exit code; boot не підміняється build |
| E. Install-path evaluation | Guix-native deployment споживає prebuilt closure, зберігаючи generation/rollback semantics | Окремий review Guix backend і ручний acceptance до будь-якої мутації диска |

Етап E не входить у цей PR і не дозволяє реалізувати destructive apply. Поточний installer backend ще не виконує повний physical deployment; цей план не змінює його статусу.

## Висновок

Запозичуємо з Omarchy **ідею не повторювати однакову роботу при кожній інсталяції**, а не його root-image unpack implementation. Для WSM кандидат — перевірене повторне використання Guix store outputs із точними pinned inputs, авторизованими підписами й повною provenance. Поки що це план дослідження; channel locks, substitute trust, live recipe, system backend і rollback не змінюються.
