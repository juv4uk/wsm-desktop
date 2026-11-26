# Політика продуктивності та CPU-оптимізацій WSM

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **початкова архітектурна політика; реалізація поетапна**
- Критичний шлях до Hardware Preview RC1: **ні**
- Батьківське завдання: [#147 — принципи Clear Linux у WSM](https://github.com/juv4uk/wsm-desktop/issues/147)
- CPU evidence/runtime dispatch: [#148](https://github.com/juv4uk/wsm-desktop/issues/148)
- Профілі Guix: [#149](https://github.com/juv4uk/wsm-desktop/issues/149)
- Stateless-конфігурація: [#150](https://github.com/juv4uk/wsm-desktop/issues/150)
- Performance baseline: [#151](https://github.com/juv4uk/wsm-desktop/issues/151)

## 1. Мета та джерело ідей

WSM запозичує з Intel Clear Linux OS принцип holistic performance engineering: оцінювати продуктивність на рівні системи, toolchain, бібліотек, runtime та порядку запуску служб, а не зводити її до одного параметра ядра.

Clear Linux описував per-package compiler flags, вибір GCC або Clang за результатами вимірювань, кілька варіантів бібліотек під CPU ISA та runtime dispatch. Це цінні інженерні практики, але не готова база для WSM: Clear Linux був оптимізований передусім для платформ Intel і більше не є підтримуваним дистрибутивом. WSM використовує його документацію як історичне джерело дизайну, а реалізацію будує на активному upstream та GNU Guix.

Джерела:
- [Clear Linux — Performance](https://clearlinux.github.io/clear-linux-documentation/guides/clear/performance.html)
- [Clear Linux — About](https://clearlinux.github.io/about.html)
- [GCC — Function Multiversioning](https://gcc.gnu.org/onlinedocs/gcc/Function-Multiversioning.html)
- [GNU Guix — Using the Configuration System](https://guix.gnu.org/manual/en/html_node/Using-the-Configuration-System.html)

## 2. Архітектурні інваріанти

1. **Portable baseline завжди існує.** Базова система та кожна критична бібліотека повинні працювати на мінімальній апаратній платформі, явно визначеній WSM.
2. **Не використовувати глобальний `-march=native`.** Він прив'язує артефакт до CPU машини-збирача і може зробити систему незавантажуваною на іншому ПК.
3. **Не робити Intel vendor check замість capability check.** Рішення ґрунтується на доступному наборі ISA features, а не на рядку vendor/model.
4. **Спеціалізована реалізація — лише оптимізація.** Вона не змінює семантику програми; portable implementation залишається fallback.
5. **Runtime-visible capabilities не є гарантією функціональної сумісності пристрою.** CPU ISA facts не замінюють driver/firmware evidence і не означають, що GPU чи інший пристрій працює.
6. **Жодних автоматичних hardware mutations.** Preflight не змінює governor, частоти, power limits, MSR, firmware чи системні налаштування.
7. **Вимірювання важливіші за припущення.** Compiler, flags, бібліотеку або boot sequence змінюємо лише тоді, коли повторюваний тест показує виграш без регресії сумісності.

## 3. CPU capability evidence

### Поточний стан

Hardware report v1.0.0 містить CPU model/vendor як identity, але не має нормалізованого поля ISA capabilities. У v1.0.0 об'єкти закриті через `additionalProperties: false`; отже додавання нових полів до наявного звіту без зміни версії порушило б контракт.

**Не додавати CPU flags до v1.0.0.** Пропозиція для v1.1.0 та сумісність producer/consumer ведуться окремо в #148 і #5.

### Пропоноване джерело та семантика

Для першої x86-реалізації розглядати лише kernel-exposed feature flags з `/proc/cpuinfo`. Не читати довільні MSR і не виконувати власні привілейовані CPUID-послідовності. Не записувати весь raw `cpuinfo` у звіт.

- Збирати intersection flags для всіх online logical CPUs, а не лише першого процесора. Це консервативна спільна множина, без припущень про scheduler-aware dispatch на heterogeneous cores.
- Фіксувати, що це можливості, видимі поточному Linux kernel/process environment. Hypervisor, kernel policy або container можуть приховувати частину features.
- Відсутнє, неповне чи некоректне джерело дає `unknown`, а не `unsupported`.
- Не виводити ISA level з CPU model string.
- Для ARM та інших архітектур використовувати окремі архітектурні vocabulary; не мапити їх на x86 labels.

Майбутній report field має містити нормалізовані feature identifiers, provenance, observation time та scope. Raw feature line не потрібний. Schema evolution повинна зберігати окремий validator для кожної підтримуваної версії.

## 4. Runtime dispatch та спеціалізовані бібліотеки

GCC підтримує function multiversioning: декілька реалізацій функції можуть бути скомпільовані для різних ISA extensions, а resolver обирає сумісну реалізацію під час виконання. Це приклад для вибіркових CPU-intensive routines, а не дозвіл збирати весь дистрибутив із найновішими прапорцями.

Правила WSM:

- Починати з portable implementation і визначеної baseline ABI.
- Додавати спеціалізований варіант лише до конкретної бібліотеки/функції з виміряним workload.
- Використовувати перевірений runtime resolver із upstream toolchain; не реалізовувати власний низькорівневий dispatcher без потреби.
- Resolver має перевіряти всі необхідні CPU та OS-enabled features. Для AVX-family не можна вважати одного hardware flag достатнім, якщо середовище не підтвердило підтримку відповідного extended state.
- При невідомій capability, невдалому resolver або непідтримуваному CPU обирається portable fallback.
- Артефакти збираються з pinned Guix inputs і відтворюваними параметрами. Host CPU збирача не може непомітно визначати ABI релізного артефакту.

Перший кандидат на optimization pilot має бути бібліотекою з обмеженим hot path і хорошим тестовим набором. Жоден кандидат не вибирається заздалегідь без benchmark.

## 5. Compiler та package policy

- GCC — початковий стандартний toolchain, якщо конкретний package не має доведеного виграшу від іншого компілятора.
- Clang/LLVM дозволяється на рівні окремого package, коли upstream підтримка, коректність та повторювані benchmarks виправдовують його.
- Compiler flags фіксуються per-package у Guix package definition/variant, а не глобально для всієї системи.
- Не переносити патчі Clear Linux автоматично. Спочатку шукати upstream-реалізацію; локальний patch потребує окремого owner, тестів і плану видалення після upstream merge.
- Не змінювати optimisation level, LTO, PGO або linker flags лише заради красивої конфігурації. Для кожного рішення записати вимірюваний результат і вплив на розмір/час збірки.
- Розмір closure, час збірки та час виконання — різні виміри; не оптимізувати один, замовчуючи інші.

## 6. Профілі системи замість паралельного package manager

Ідею Clear Linux functional bundles реалізувати нативними Guix manifests та Guix System configuration. Кандидати: Desktop, Developer, Creator і явно опційний Compatibility. Їхній склад, залежності, ліцензії та pinned availability визначає #149.

WSM не додає `swupd`, RPM, окремий bundle database чи другий activation manager. Власником системних пакетів, служб, generations і rollback залишається Guix System згідно з ADR 0004.

## 7. Stateless та відновлення

Stateless означає чітке розділення власності, а не відсутність стану:

- immutable package artifacts належать Guix store;
- системна декларація та системні служби належать Guix System generation;
- administrator overrides мають явний шлях, precedence та перевірку конфліктів;
- користувацькі налаштування й документи належать користувачеві та переживають reconfigure;
- кеші, тимчасові файли та runtime state мають визначену політику очищення;
- secrets/credentials не вбудовуються в world-readable generation або звіти.

Точні шляхи, ownership, retention та rollback semantics визначає #150. WSM не переписує вручну файли, якими керує Guix, і не створює власного system activation manager.

## 8. Performance measurement

Benchmarks не входять до звичайного hardware preflight.

Кожен вимір повинен фіксувати: commit, Guix channel revision, kernel, toolchain, package flags, CPU architecture/visible feature set, RAM, storage class, virtualization mode, power/governor state, command, repetitions та exit status.

- QEMU/TCG результати відокремлювати від фізичного обладнання.
- Виконувати щонайменше п'ять повторів; публікувати median та MAD або p90.
- Відділяти cold start від warm start і build time від runtime.
- Boot analysis має визначати окремі milestones і critical path служб, а не лише один загальний час.
- Regression threshold вводити лише після накопичення стабільної baseline на конкретному runner/hardware class.
- Відсутній або зашумлений результат має стан `unknown`; не підміняти його нулем чи pass.

Пілотний протокол та harness ведуться у #151.

## 9. Режими живлення

Performance governor не є універсальним desktop default. WSM не копіює глобальне правило Clear Linux про максимальну частоту CPU на кожній машині.

Можливі користувацькі режими — Balanced, Performance та Power Saving — потребують окремого дослідження. Перемикання має бути явним, оборотним, видимим у UI та коректним для підтримуваних драйверів/CPU. Невідомий або недоступний power control не повинен блокувати завантаження. До завершення #151 жоден такий режим не заявляється як реалізований.

## 10. Етапи впровадження

1. Зафіксувати цю policy та перевірити її відповідність Guix-first ADR.
2. У #148 погодити report v1.1.0 CPU evidence contract без зміни v1.0.0.
3. У #149 визначити перший мінімальний Guix Desktop profile та його package closure.
4. У #150 визначити stateless ownership/rollback contract до появи реального installer APPLY.
5. У #151 створити reproducible benchmark baseline.
6. Лише після цього вибрати одну бібліотеку для runtime-dispatch pilot і виміряти її на щонайменше двох різних hardware classes.

## 11. Що не переносимо

- Intel-only CPU assumptions або вимогу AVX2/AVX-512 для базового boot.
- Глобальний `-march=native`.
- Performance governor як обов'язкове налаштування.
- Архівні Clear Linux package manager/build tools як паралельну інфраструктуру.
- Не перевірені patches/compiler flags та performance claims без benchmark evidence.
- Stress tests або power/thermal tuning у read-only preflight.
