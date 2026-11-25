# Контракт передавання: апаратний preflight → план → системний backend

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Статус: **proposed / design-only** — backend-адаптер Guix v0.1 реалізовано read-only
- Дата: 2026-11-25
- Основне завдання: [#12](https://github.com/juv4uk/wsm-desktop/issues/12)
- Батьківський напрям: [#10 — hardware-first installer](https://github.com/juv4uk/wsm-desktop/issues/10)
- Вхідні контракти: [#5 — hardware evidence report](https://github.com/juv4uk/wsm-desktop/issues/5), [#6 — wsm-hwcheck](https://github.com/juv4uk/wsm-desktop/issues/6)
- Межі інтеграції: [#7 — preflight integration](https://github.com/juv4uk/wsm-desktop/issues/7), [#13 — read-only installer prototype](https://github.com/juv4uk/wsm-desktop/issues/13)
- Архітектурне правило: [ADR 0004](decisions/0004-nix-guix-backend-strategy.md)

## 1. Призначення та межі

Цей документ визначає контракт між трьома незалежними частинами WSM:

1. **Hardware collector** спостерігає обладнання та формує версійований звіт.
2. **Installer frontend** перевіряє звіт, пояснює користувачеві стан пристроїв і формує план інсталяції.
3. **Рівно один native backend** перевіряє та виконує підтверджений план відповідно до власної моделі системи.

Контракт не обирає Calamares, Nix чи Guix як остаточну реалізацію. Він не є кодом інсталятора і не дозволяє запис на диск. Перша реалізація в межах #13 має залишатися read-only та завершуватися створенням draft plan.

**Базовий принцип:** WSM не переписує системні пакетні менеджери, драйверні бази або механізми розгортання. Він повторно використовує upstream-інструменти, нормалізує докази й передає підтриманий намір користувача штатному backend-у.

## 2. Вхідний контракт: hardware evidence report

Джерело — версійований JSON-звіт із #5, який створює collector із #6.

Поточний прототип #6 має такий CLI-контракт:

- `python3 -m wsm_hwcheck` — JSON у stdout;
- `python3 -m wsm_hwcheck --output PATH` — локальний JSON-файл;
- `--version` — версія collector;
- за відсутності параметрів тестових коренів читаються лише системні `/sys` та `/proc`.

Інсталятор може приймати готовий звіт через `--report PATH` або запускати collector як окремий процес і захопити stdout. У першому прототипі бажано використовувати явний файл у тимчасовому каталозі live-сесії: це дає змогу перевірити, показати й повторно прочитати той самий snapshot. Сам факт створення локального тимчасового звіту не є дозволом змінювати цільовий диск.

### 2.1 Перевірки звіту

Перед використанням installer повинен:

1. Переконатися, що JSON читається повністю й відповідає очікуваному типу даних.
2. Перевірити `schema_version` та валідовувати документ відповідною локальною версією JSON Schema.
3. Переконатися, що `report_id`, `collected_at`, `environment`, `collectors`, `devices` і `privacy` присутні.
4. Відхилити непідтримувану major-версію з повідомленням, що саме несумісне. Не намагатися «вгадати» семантику нової схеми.
5. Перевірити architecture, kernel release, boot mode та `collected_at` проти поточного середовища. Для schema v1.0.0 це лише перевірка узгодженості середовища й грубої часової давності: схема не містить boot-session identity або monotonic collection time, тому ці поля **не доводять**, що звіт створено в поточному boot session.
6. Якщо сценарій або політика підтвердження вимагає доказу тієї самої live-сесії, а такий доказ відсутній у вибраній версії схеми, позначити freshness як `unverifiable`, запросити новий збір або окрему версіоновану freshness envelope. Не перетворювати `collected_at` чи збіг kernel/architecture/boot mode на доказ поточної boot-сесії.
7. Зберегти provenance кожного використаного факту: джерело, версію інструмента, час, confidence та evidence kind.

Невідоме значення залишається `unknown`; відсутність optional-інструмента не перетворюється на `failed` чи `unsupported`. Відсутність пристрою у звіті не завжди означає, що фізичного пристрою немає.

### 2.2 Заборонені припущення

- `discovered` не означає, що пристрій працездатний.
- `driver.status = bound` не доводить функціональну працездатність.
- Наявний файл firmware не доводить, що ядро завантажило саме його.
- Наявність пакета в індексі не доводить, що він доступний у вибраній ревізії каналу або вже присутній у live image.
- Зовнішній запис для схожої моделі не є підтвердженням для конкретної ревізії плати, ядра та шляху підключення.
- Відсутність запису в зовнішній базі не є доказом несумісності.

### 2.3 Не згортати фізичну топологію пристроїв

Frontend зберігає різницю між фізичним пристроєм, його функціональними інтерфейсами та підключеними до нього шляхами:

- USB composite device може мати кілька інтерфейсів із різними class/subclass/protocol та різними driver bindings. Не класифікувати весь пристрій за одним `bDeviceClass`, якщо функції описані на interface nodes.
- GPU, DRM connector і фізичний monitor — різні сутності. Один GPU може мати кілька connector-ів; монітор не можна визначати лише за назвою connector-а.
- Коли report/schema надає явні relationship IDs, installer показує ці зв'язки. Коли зв'язок не зібраний або не представлений поточною версією схеми, він залишається unknown; frontend не виводить його лише з подібних назв чи порядку пристроїв.
- Inventory observation (наприклад, `connector status = connected`) не є успішним functional test. `functional_tests.status = passed` зарезервований для конкретної функції з описаним методом та результатом; сам факт читання sysfs належить до inventory/evidence.

Це правило має діяти навіть тоді, коли початкова схема ще не підтримує повну топологію. Відсутність relationship field означає, що зв'язок невідомий, а не що пристрої не пов'язані. Будь-яке додавання полів для device/interface/connector relationships робиться в межах #5 із версіонуванням схеми, а не локальним розширенням installer-а.

### 2.4 Межі поточного collector-а

Поточний `wsm-hwcheck` v0.1.0 із #6 є **inventory-only** реалізацією: він читає локальні `/sys` і `/proc`, але не виконує функціональних тестів і ще не збирає повні driver/runtime-firmware докази. Тому installer не має підвищувати відсутні дані до позитивних або негативних висновків:

- Якщо поле драйвера присутнє у звіті як безпосереднє sysfs binding, показати саме binding observation; якщо collector його не зібрав, показати `unknown` або `not-collected`.
- Runtime firmware `loaded`, `missing` чи `load-error` не можна виводити лише з наявності файлу firmware або з PCI/USB enumeration. До появи перевіреного kernel-log/runtime collector-а цей стан залишається `unknown`.
- Функціональний статус `passed` не можна генерувати на основі inventory. Installer показує `not-run` для тестів, які фактично не запускалися.
- USB interface-level driver binding, GPU→DRM connector, connector→monitor та інші зв'язки, яких немає у v1 report, залишаються unknown до версійованого розширення в #18/#5.

Ці обмеження — властивість поточного джерела даних, а не недолік, який frontend може «виправити» евристикою.

## 3. Оцінка готовності: результат по пристроях, не загальний бал

Installer формує похідну оцінку для кожного критичного пристрою, зберігаючи оригінальний evidence report незмінним.

Рекомендовані стани інтерфейсу:

| Стан | Значення | Типова поведінка |
| --- | --- | --- |
| `ready-tested` | потрібна функція пройшла прямо задокументований тест | показати тест, дату та джерело |
| `ready-detected` | пристрій виявлений, шлях/драйвер видимий, але повний тест не виконаний | попередження без твердження про повну підтримку |
| `warning` | є відомий дефект, firmware issue або обмеження, але безпечний альтернативний шлях можливий | пояснити наслідок і альтернативу |
| `unknown` | доказів недостатньо або джерело недоступне | не прирівнювати до помилки; дати ручний шлях перевірки |
| `blocked` | підтверджено умову, за якої продовження небезпечне або технічно неможливе | не дозволяти перейти до плану без усунення причини |

Рішення приймається окремо для фактичних вимог обраного сценарію. Наприклад, Wi-Fi, що не перевірений, не повинен автоматично блокувати встановлення, якщо є перевірений Ethernet або offline path. Невідомий стан audio або Bluetooth не повинен блокувати інсталяцію системи. Натомість відсутність доступного цільового диска, ненадійний storage path або відсутній працездатний input/display path можуть зробити безпечне встановлення неможливим.

**Критичні невідомі — сценарій-залежні.** Невідомий стан не блокує інсталяцію сам по собі, але якщо невідомість стосується обов'язкової передумови саме обраного сценарію, installer не створює executable disk plan, доки користувач не вибере перевірену альтернативу або не з'явиться потрібний доказ. Наприклад, інтерактивний сценарій потребує принаймні одного придатного шляху введення та відображення; мережевий сценарій потребує підтвердженого мережевого шляху; offline-сценарій може продовжитися без Wi-Fi. Для storage target неоднозначна ідентифікація завжди є hard stop. Draft diagnostic summary дозволений, але не повинен виглядати як план, готовий до підтвердження.

Hard-stop має містити стабільний reason code, конкретний пристрій/факт, evidence reference та зрозуміле пояснення. Заборонено створювати один сумарний «compatibility score», який приховує причину рішення.

## 4. План інсталяції: поточний CLI v0.1 та цільовий handoff-контракт

Installer не змінює та не дописує hardware report. Він створює окремий reviewable install plan, який описує **намір користувача**, обраний backend і майбутні дії.

**Важливо розрізняти реалізований JSON v0.1 та майбутню логічну модель.** Поточний CLI з #19 формує тільки diagnostic-only dry-run plan. Таблиця цільових полів нижче описує напрям подальшого контракту; вона **не** є JSON shape, який уже повертає CLI v0.1. Реалізована структура наведена окремо в §4.1.

| Поле | Вимога |
| --- | --- |
| `plan_version` | Версія контракту install plan |
| `plan_id` | Випадковий ідентифікатор цього плану, не host ID |
| `created_at` | Час формування плану |
| `source_report` | `schema_version`, `report_id`, SHA-256 точних байтів звіту |
| `backend.id` | Рівно одне значення: `guix-system` або `nixos` |
| `backend.revision` | Точна ревізія каналів/inputs або явне `unlocked` для суто експериментального dry-run |
| `user_intent` | Підтримані locale, timezone, keyboard, profile та інші вибрані користувачем параметри |
| `storage` | Явно обраний диск, mount plan, filesystem plan та boot target |
| `hardware_decisions` | Рішення користувача щодо попереджень і дозволених альтернатив, прив'язані до evidence refs |
| `software_policy` | Free/Compatibility policy, package sources та політика firmware |
| `execution.mode` | `dry-run` або `confirmed` |
| `execution.mutations_authorized` | За замовчуванням `false`; стає `true` тільки після окремого підтвердження незмінного плану |

### 4.1 Реалізований CLI/plan v0.1 (#19)

Поточна read-only реалізація приймає вже створений hardware report і не запускає collector самостійно:

```sh
python3 -m wsm_install --preflight \
  --report /path/to/report.json \
  --backend guix --dry-run
```

CLI contract v0.1:

- `--preflight` і `--dry-run` обов'язкові.
- `--report PATH` обов'язковий; CLI не викликає `wsm_hwcheck` і не читає collector stdout напряму.
- `--backend` приймає лише alias `guix` або `nix`; вони відображаються на plan IDs `guix-system` та `nixos`.
- JSON plan надходить у stdout за замовчуванням; optional file output задається як `--plan-output PATH`. Опції `--output` немає.
- `--quiet` приглушує human-readable summary у stderr і не змінює JSON plan.
- `--version` виводить `wsm-install 0.1.0`.
- Exit codes: `0` — звіт валідований і план видано; `2` — CLI/input/JSON/schema/output-path error; `3` — critical evidence unresolved, plan не видається.
- CLI не має apply/confirm option. Кожен план v0.1 має `plan_status=diagnostic-only` та `plan_readiness.confirmable=false`; це не executable deployment plan.

Реалізований JSON v0.1 містить:

- `plan_version=0.1.0`, `plan_mode=dry-run`, `plan_status=diagnostic-only`;
- `plan_readiness`, зокрема `confirmable=false`, `missing_required_roles`, `role_coverage` та `required_user_actions`;
- `backend.id`;
- `source_report` з schema version, report ID і SHA-256 точних raw bytes;
- `environment`, `device_summary`, `warnings` та `blockers`;
- `execution` booleans: `dry_run`, `plan_confirmable`, `mutations_authorized`, `backend_invoked`, `disk_access_performed`.

Усі v0.1 плани залишаються diagnostic-only, навіть коли blocker list порожній: це не означає, що вже реалізовано user confirmation, storage/partition plan або backend apply. Поточний CLI не реалізує повний target model з §4: зокрема storage partition plan, selected/pinned backend revision, повний user intent, confirmation token і apply phases ще не існують у його JSON output.

**Coverage marker і verdict — різні поняття.** Якщо report не містить запису потрібної capability, CLI може відобразити це в `plan_readiness.role_coverage` як `not-collected` і додати warning. Похідний compatibility verdict цієї capability має залишатися `unknown` із збереженням причини, coverage boundary та provenance; `not-collected` не є verdict, не означає `not-detected` або `not-tested` і не задовольняє critical evidence gate. Такий missing-role план залишається diagnostic-only.

**Freshness у CLI v0.1 не реалізована.** CLI перевіряє schema і записує report timestamp/environment, але не доводить same-boot identity, monotonic collection age або незмінність topology у поточній boot-сесії. Тому збіг `collected_at`, architecture та kernel не можна називати перевіркою поточної сесії. PR #41 — окремий consumer-side freshness policy prototype; він не інтегрований у CLI та залишається pending producer/schema approval від #5/#6. До появи узгоджених versioned report fields same-session freshness для confirmation є `unverifiable`.

### 4.2 Канонічні digest-и та точні байти

Щоб незалежні frontend/backend реалізації обчислювали однакові значення:

- `source_report.sha256` — SHA-256 **точних raw bytes** файлу звіту до JSON parsing або будь-якого re-serialization. Не хешувати нормалізований JSON замість початкових байтів.
- Для `plan_sha256` спочатку створити весь об'єкт плану **без поля `plan_sha256`**, серіалізувати його як UTF-8 JSON із `ensure_ascii=false`, сортуванням ключів (`sort_keys=true`) і роздільниками `(",", ":")` без пробілів/pretty-print, а потім обчислити SHA-256 цих байтів. Лише після цього додати `plan_sha256` до об'єкта.
- Кінцевий newline для файлу/STDOUT не входить до hashed canonical bytes. Порядок полів у вхідному report не змінює його raw-byte digest; будь-яка зміна байтів report створює інший digest.

Це відповідає реалізації прототипу #13: canonical JSON UTF-8, sorted keys, compact separators, digest додається після хешування об'єкта. Не вводити інший canonicalization profile без зміни versioned contract.

Ця таблиця визначає семантику, а не остаточний JSON Schema. Точний versioned plan schema має бути окремою реалізаційною зміною після затвердження контракту.

### 4.3 Посилання на цільовий диск

Цільовий диск не можна обирати за індексом на кшталт «перший диск» або за раніше збереженим `/dev/sda` без повторної перевірки. UI повинен показати користувачеві модель, місткість, тип підключення та фактичний target path, доступні у поточній сесії.

План може тримати короткоживучий target reference, але перед першим записом backend зобов'язаний повторно розв'язати його в поточну block-device identity та перевірити, що це той самий пристрій і що всі partition/mount assumptions залишаються чинними. Якщо відповідність змінилася — підтвердження плану анулюється.

**Актуальність hardware report ніколи не замінює повторну ідентифікацію target device.** Безпосередньо перед першою destructive дією backend має незалежно перечитати поточну block-device identity, порівняти її з тим target, який користувач явно вибрав і підтвердив, а також повторно перевірити partition/mount assumptions. Будь-яка невідповідність або неоднозначність анулює confirmation і зупиняє apply.

Raw serial, WWN, UUID та інші чутливі ідентифікатори не додаються до hardware report або загальних логів. Якщо системний backend технічно потребує такого ідентифікатора для локальної операції, він зберігається лише в мінімальному локальному контексті, не експортується й не потрапляє до звітів за замовчуванням.

### 4.4 Незмінність після підтвердження

Після підтвердження плану будь-яка зміна backend, target disk, partition map, boot mode, profile, firmware choice або іншого параметра, який впливає на наслідки інсталяції, створює нову версію плану та вимагає нового підтвердження. Підтвердження старої версії не переноситься автоматично.

## 5. Backend handoff: один власник однієї системи

Backend є єдиним компонентом, який знає, як конкретна система будується, активується та встановлюється. Frontend не генерує shell-команди з довільного тексту користувача.

Підтримувані значення в цьому контракті:

- `guix-system` — Guix-native declaration і Guix deployment path;
- `nixos` — NixOS-native configuration і NixOS deployment path.

Для однієї інсталяції дозволено вибрати **лише один** backend. Не можна об'єднувати `/gnu/store` і `/nix/store`, передавати один і той самий root filesystem двом системним менеджерам, запускати обидва механізми активації або дозволяти обом встановлювати bootloader.

Backend contract має реалізувати окремі кроки:

1. **Validate** — read-only перевірка плану, сумісності backend-а, mount plan, target references, policy та потрібних даних.
2. **Realize/build** — побудова або отримання потрібного системного closure у межах обраного backend-а, без запису на цільовий диск.
3. **Prepare** — повторна перевірка target devices та підготовка точного набору операцій. Жодних прихованих side effects.
4. **Apply** — єдина контрольована точка, де після підтвердження починаються операції з цільовим диском.
5. **Verify** — перевірка результату та формування звіту про те, що фактично відбулося.

Цей контракт не вимагає вручну компілювати драйвери, kernel або пакети. Backend використовує свої штатні package definitions, довірені канали/inputs і доступні перевірені substitutes. Власна збірка пакета — звичайний механізм backend-а, а не ручна процедура для кожного пристрою. WSM не додає невідомі binary caches, signing keys, сторонні репозиторії чи nonfree компоненти автоматично. Якщо потрібного пакета немає в обраних джерелах, результатом є зрозуміле обмеження/unknown, а не імпровізоване завантаження драйвера з випадкового сайту.

### 5.1 Власність над системними компонентами

У межах конкретного backend-а тільки він керує:

- root filesystem deployment;
- системними обліковими записами та системними службами;
- bootloader і boot entries у межах його штатної моделі;
- активацією конфігурації та системними поколіннями;
- встановленням package/firmware closure.

Frontend передає параметри й показує план. Він не запускає stock bootloader job паралельно з backend-ом і не вважає generic user-creation module заміною декларативних user accounts.

## 6. Порядок виконання та точки безпеки

Стандартна послідовність:

```text
LIVE_BOOT
   |
   v
COLLECT_REPORT (read-only)
   |
   v
VALIDATE_REPORT
   |
   v
ASSESS_CRITICAL_DEVICES
   |
   v
BUILD_DRAFT_PLAN (no target writes)
   |
   v
SHOW_EXACT_PLAN_AND_WARNINGS
   |
   v
USER_CONFIRMATION
   |
   v
BACKEND_VALIDATE (read-only)
   |
   v
BACKEND_REALIZE (no target writes)
   |
   v
REVALIDATE_TARGET_AND_PLAN
   |
   v
BACKEND_APPLY (first target-disk mutation)
   |
   v
BACKEND_VERIFY
```

До переходу в `BACKEND_APPLY` заборонені:
- створення/видалення partition table або filesystem на цільовому диску;
- зміна mount state цільової системи, яка не є read-only inspection;
- запис у EFI variables або boot entries;
- встановлення bootloader;
- виклик `guix system init`, `nixos-install` або еквівалентної команди розгортання;
- firmware update, довільне завантаження модулів або package installation у host environment.

Temporary files у live environment дозволені лише для звіту, плану та журналу без секретів. Ці файли не можуть непомітно зберігатися на цільовому диску.

### 6.1 Помилки

- Помилка до `USER_CONFIRMATION` залишає план у draft/invalid стані.
- Помилка у `BACKEND_VALIDATE` або `BACKEND_REALIZE` не повинна запускати disk mutation.
- Перед `BACKEND_APPLY` backend повторно перевіряє target identity та незмінність підтвердженого плану.
- Помилка після першого запису не приховується й не запускає сліпий «rollback». Backend зберігає стан операції, повідомляє, що вже було змінено, і надає безпечну процедуру продовження або відновлення.

## 7. Приватність та аудит

- Default mode — offline; hardware report не надсилається мережею.
- Network lookup або probe upload, якщо колись з'являться, є окремою опційною дією з окремою згодою.
- Не передавати serial numbers, MAC, UUID, hostname, username, IP чи storage WWN за замовчуванням.
- Логи фіксують версії collector/schema/installer/backend, hash report та plan, команди як масив аргументів (не shell string), exit code і фазу операції.
- Секрети, паролі, токени та приватні ідентифікатори не потрапляють у логи.
- Усі backend inputs мають мати точні ревізії або явний статус незакріпленого експерименту; невідомі ключі довіри не додаються автоматично.

## 8. Мінімальні acceptance assertions

Цей контракт вважається реалізованим лише тоді, коли автоматичні тести доводять таке:

1. Невалідний JSON, відсутній report або непідтримуваний major version не дають створити install plan.
2. Валідний звіт із невідомими не-критичними пристроями не блокує draft plan.
3. Відсутність зовнішньої бази або мережі не перетворюється на негативний висновок.
4. Немає вибраного backend-а або обрано більше одного backend-а — handoff неможливий.
5. План містить точні посилання на report ID/version/hash та evidence refs для кожного прийнятого hardware decision.
6. Зміна target disk identity або будь-якого критичного параметра після підтвердження анулює confirmation.
7. `--dry-run` закінчується до будь-якого доступу на запис до target disk та до backend apply command.
8. У тестах Guix path не запускається NixOS deployment і навпаки.
9. Передача довільного тексту користувача не створює shell command injection; backend отримує типізовані поля й allow-listed argv.
10. Журнал не містить секретів та чутливих апаратних ідентифікаторів за замовчуванням.
11. Помилка build/realize не запускає жодної операції з цільовим диском.
12. Усі невідомі/неперевірені функції залишаються позначеними як unknown/not-tested.

## 9. Розподіл реалізації

| Issue | Власник відповідальності | Що передає далі |
| --- | --- | --- |
| #5 | Hardware report contract | Версійований evidence JSON та правила його семантики |
| #6 | Hardware collector | Локальний report, stdout/файл, read-only гарантії |
| #7 | Installer integration | Час запуску preflight і порядок до будь-якого disk write |
| #12 | Цей документ | Узгоджений handoff contract, acceptance assertions |
| #13 | Installer prototype | Draft plan та dry-run UI/CLI без виклику backend apply |
| #14 | QEMU integration harness | Доказ порядку фаз у disposable VM |
| #2 | Backend strategy | Вибір primary backend або двох окремих редакцій після доказів |

Frontend реалізація може змінюватися (Calamares, інший GUI або TUI), але ці межі залишаються стабільними. Backend-specific конфігурація, команди й політики залишаються в окремому adapter-і.

## 10. Що не входить у цей контракт

- Вибір переможця між Guix і NixOS.
- Остаточний вибір installer frontend.
- Підтримка фізичного обладнання або сертифікація пристроїв.
- Автоматична установка proprietary firmware чи drivers.
- Реалізація partitioner, filesystem tools або bootloader.
- Мережеве надсилання hardware probe.
- Дозвіл на запуск інсталяції на фізичній машині.

Це дизайн-контракт для review. Реальне встановлення на фізичний диск залишається поза межами #12 і #13.

## 11. Стан реалізації

Контракт описано повністю, реалізовано поки що одну його частину.

**Реалізовано** — `wsm_install/backend_guix.py`, адаптер для обраного backend-а:

- відмовляє будь-якому плану, який не підтверджений, має блокери, не є `dry-run` або вже заявляє про доступ до диска;
- приймає лише `guix-system`; команди NixOS із цього модуля недосяжні;
- перевіряє кожне значення вибору користувача за allow-list, тому текст користувача не стає ні shell-командою, ні Scheme-синтаксисом;
- генерує `operating-system` декларацію, яка володіє файловими системами, обліковими записами, службами та bootloader;
- відмовляється працювати, якщо хтось додає другий bootloader job: в однієї системи один власник;
- повертає argv як типізований список, а не рядок для shell;
- анулює підтвердження, якщо після нього змінився план або вибір цілі.

**Не реалізовано** — кроки `REALIZE` та `APPLY`: адаптер не виконує `guix system init`, не монтує цільовий диск і не перевіряє його ідентичність перед записом. Це наступний крок і він потребує середовища з Guix.

Тести: `tests/test_backend_guix.py` (20 тестів) покривають відмови з розділу 8 і не потребують Guix.


## Перевірка provenance на межі backend

Backend самостійно перевіряє `source_report.report_id` як 16–80 ASCII символів `[A-Za-z0-9_-]` і `source_report.sha256` як рівно 64 lowercase hex. Обидва поля потрапляють у Scheme-коментар згенерованої конфігурації, тому backend не покладається лише на попередню JSON Schema/collector перевірку: newline та стороння Scheme-форма відхиляються навіть після повторного обчислення `plan_sha256`. Це також захищає прямі виклики `prepare()` поза installer CLI.
