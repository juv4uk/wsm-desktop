# Матриця сценаріїв інсталяції та достатності апаратних доказів

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **proposed / policy draft**
- Пов'язано: [#3 — hardware preflight](https://github.com/juv4uk/wsm-desktop/issues/3), [#5 — report schema](https://github.com/juv4uk/wsm-desktop/issues/5), [#6 — collector](https://github.com/juv4uk/wsm-desktop/issues/6), [#12 — handoff contract](https://github.com/juv4uk/wsm-desktop/issues/12), [#13 — read-only installer prototype](https://github.com/juv4uk/wsm-desktop/issues/13), [#14 — QEMU harness](https://github.com/juv4uk/wsm-desktop/issues/14), [#16 — driver/runtime firmware evidence](https://github.com/juv4uk/wsm-desktop/issues/16), [#18 — topology](https://github.com/juv4uk/wsm-desktop/issues/18), [#24 — this task](https://github.com/juv4uk/wsm-desktop/issues/24)
- Вхідна модель: Hardware Evidence Report schema v1.0.0 та inventory-only collector v0.1.0 з PR #9

## 1. Призначення

Цей документ визначає, коли апаратних доказів достатньо для конкретного сценарію інсталяції. Він не визначає загальну «сумісність комп'ютера» одним балом і не дозволяє трактувати відсутність запису як доказ відсутності пристрою.

Ключове правило:

> **Достатність доказів завжди залежить від сценарію.** Невідомий Wi-Fi не блокує offline-інсталяцію. Невідомий шлях введення може блокувати локальну інтерактивну інсталяцію, але не обов'язково віддалений сценарій із незалежно перевіреним каналом керування.

Матриця є політикою над наявною схемою. Вона не додає полів до schema v1.0.0 і не змінює producer-owned код #5/#6. Якщо для безпечного рішення бракує даних, результат залишається `unknown` / `not-collected`, а необхідне розширення оформлюється окремою версією схеми.

## 2. Рівні доказів — не змішувати

| Рівень | Що можна стверджувати | Чого це не доводить |
| --- | --- | --- |
| **Discovered** | Ядро або collector побачив пристрій у конкретному джерелі | Що є драйвер, firmware або працездатна функція |
| **Driver-bound** | У момент спостереження пристрій прив'язаний до драйвера | Що драйвер успішно виконує потрібну функцію |
| **Firmware evidence** | Є конкретний runtime-стан або повідомлення ядра про firmware | Що firmware присутня у live image, initrd чи майбутній системі |
| **Functional test** | Конкретний тест функції завершився з указаним результатом | Що всі інші функції пристрою працюють |
| **User-confirmed path** | Користувач підтвердив практичну придатність конкретного шляху в цій live-сесії | Що цей шлях гарантовано працюватиме після інсталяції або з іншим ядром |

Усі твердження мають зберігати джерело, час, метод і межі спостереження. `functional_tests.status = passed` дозволений лише для фактично виконаного тесту з описаним методом. Читання sysfs/DRM connector state — inventory observation, а не автоматично end-to-end test.

## 3. Семантика відсутніх даних

Розрізняти чотири випадки:

1. **Пристрій присутній і виявлений** — у report є device record з `discovery_status = discovered`.
2. **Пристрій явно не виявлений у межах задекларованого покриття** — допустиме лише тоді, коли collector справді перевірив відповідне джерело/клас пристроїв і це покриття задокументоване.
3. **Пристрій або функція невідомі** — запис має `unknown`, або доказу недостатньо.
4. **Клас/функція не збиралися** — `not-collected` на рівні пояснення/результату сценарію; не підміняти цим `not-detected`.

У schema v1.0.0 немає повного coverage manifest для кожного класу пристроїв. Наявність collector у `collectors[]` і його `scope` сама по собі не доводить, що він перевірив input events, мережеву доступність, фактичне відтворення аудіо чи запис на диск. Тому v1 consumer не повинен виводити «пристрою немає» з порожнього або неповного списку.

Якщо потрібний сценарію клас не покритий поточним collector-ом, результат — **unknown/not-collected**, а не ready і не несумісний. UI має пояснити, який доказ відсутній і як користувач може перевірити альтернативний шлях.

## 4. Матриця сценаріїв

### 4.1 Локальна інтерактивна інсталяція

| Capability | Мінімум для продовження | Якщо доказу немає |
| --- | --- | --- |
| Поточний live boot | Поточна сесія справді завантажилася; зафіксовані архітектура, kernel release і boot mode | Не робити висновок про підтримку майбутнього bootloader |
| Display | Виявлений connected DRM connector та активний mode — початковий inventory evidence; користувач підтверджує, що бачить і може читати інтерфейс | Hard-stop для локального інтерактивного сценарію, доки не обрано перевірений альтернативний display/control path |
| Input | Користувач підтверджує фактичну дію через keyboard/mouse/touch або інший input path у live-сесії | Hard-stop для локального інтерактивного сценарію; просте виявлення USB/HID-пристрою недостатнє |
| Storage target | Користувач окремо вибирає ціль; її identity перевіряється безпосередньо перед будь-якою операцією запису | Не створювати підтверджуваний destructive plan без однозначної цілі |
| Runtime firmware | Для функції, обов'язкової цьому сценарію, `missing` / `load-error` — blocker; `unknown` / `available-not-confirmed-loaded` — warning/unknown залежно від альтернативи | Не робити глобального висновку про всю систему |

### 4.2 Offline-інсталяція

| Capability | Мінімум для продовження | Якщо доказу немає |
| --- | --- | --- |
| Local control | Ті самі перевірені display та input шляхи, що й для локальної інтерактивної інсталяції | Hard-stop, якщо немає альтернативного керування |
| Storage target | Окремий вибір і повторна перевірка цілі перед записом | Hard-stop для destructive phase |
| Offline software closure | Потрібні пакети, firmware та backend inputs мають бути доступні локально в live image/cache або в іншому явно обраному локальному джерелі | Це **software/artifact readiness**, не hardware discovery; якщо closure не перевірена, не обіцяти завершення offline deployment |
| Network | Не є обов'язковою умовою | Невідомий або відсутній Wi-Fi/Ethernet — не blocker |

Відсутність мережі не повинна перетворюватися на негативну оцінку сумісності пристрою, якщо сценарій offline і потрібні артефакти вже доступні.

### 4.3 Network-assisted інсталяція

| Capability | Мінімум для продовження | Якщо доказу немає |
| --- | --- | --- |
| Local control | Перевірені display та input шляхи або інший явно визначений control path | Hard-stop, якщо користувач не може керувати процесом |
| Network interface | Виявлений інтерфейс і driver binding — лише початкові докази | Не вважати це підтвердженням доступу до мережі |
| Network connectivity | Окремий read-only connectivity test до потрібного endpoint/repository з timestamp та результатом | Warning або hard-stop саме для network-assisted сценарію; запропонувати offline fallback, якщо він справді доступний |
| Repository/artifact readiness | Перевірена доступність потрібних каналів, підписів, substitute endpoints та inputs | Hardware report не може підтвердити це самостійно; backend/software preflight має надати окремий доказ |

Link state, DHCP address або наявність драйвера не доводять доступність конкретного сервера, DNS, TLS чи substitute. Не запускати мережеві перевірки автоматично в режимі, який заявлений як strict offline; така перевірка має бути явно обрана.

### 4.4 Headless / remote install

Цей сценарій не вважається підтриманим лише тому, що у звіті є Ethernet або Wi-Fi. Потрібен окремо визначений і перевірений канал керування (наприклад, serial console або remote session), його автентифікація та доступність у поточній live-сесії. До появи такого контракту headless/remote — **unsupported/unknown**, а не автоматична альтернатива відсутньому display/input.

## 5. Storage: inventory не є дозволом на запис

Hardware collector може інвентаризувати контролери та block devices. Це не означає, що він може вибрати target або перевірити безпечність знищення даних.

- Не вибирати «перший диск», `/dev/sda`, найбільший диск або попередній target автоматично.
- Не трактувати наявність block device як згоду на його використання.
- Dry-run не відкриває block device для запису, не монтує його для запису, не виконує partition/mkfs/bootloader операцій.
- Вибір користувача має бути прив'язаний до короткоживучої локальної target identity.
- Перед першою mutation target identity перевіряється повторно; зміна або неоднозначність анулює підтвердження.
- Target identity не виноситься в публічний report або звичайні логи; зберігати лише необхідний локальний контекст із privacy controls.

Поле `criticality = storage-install-target` у report не замінює цей окремий процес вибору та revalidation.

## 6. Firmware та package-source policy

Firmware має щонайменше три різні питання:

1. Чи потребує конкретна функція firmware і чи було зафіксовано runtime load result у поточній live-сесії?
2. Чи входить потрібний файл/пакет у live image та initrd на момент probe?
3. Чи буде firmware доступна в цільовій системі після встановлення?

Позитивна відповідь на одне питання не доводить інші. Пакет у package index або у майбутній target closure не доводить, що live kernel уже мав його під час ініціалізації пристрою.

WSM спершу повторно використовує підтримувані upstream kernel/driver/firmware packages і штатні Guix sources/substitutes для першого preview; Nix/NixOS залишається дослідженням і не є доступним installer backend-ом. Не компілювати драйвери вручну та не завантажувати довільні binaries лише для перетворення unknown на ready. Nonfree firmware, якщо вона потрібна, має бути явно позначена за ліцензійною політикою та окремо підтверджена для live image, initrd і target system.

## 7. Правила для #13: plan eligibility

Для першого CLI прототипу:

- Успішна JSON Schema validation — необхідна, але недостатня умова для сценарію.
- Відсутній record не можна трактувати як успішно перевірену capability.
- Наявний record з `discovery_status = unknown` або відсутній evidence coverage дає unknown, а не ready.
- Hard-stop застосовується лише до capability, обов'язкової для явно вибраного сценарію, і має reason code та evidence reference.
- Якщо CLI ще не приймає сценарій явно, він повинен називати результат **diagnostic draft only** і не позиціонувати його як підтвердження готовності до інсталяції.
- Перший preview має лише backend ID `guix-system`; майбутній backend, якщо його окремо приймуть, матиме власний ID та deployment path. Вибір backend не змінює hardware evidence.
- Draft plan не містить дозволу на mutation. Fresh report не замінює target revalidation.

### 7.1 Рекомендовані reason codes

| Code | Значення |
| --- | --- |
| `SCENARIO_NOT_SELECTED` | Не визначено, які capabilities обов'язкові |
| `CAPABILITY_NOT_COLLECTED` | Поточний collector не доводить потрібну capability |
| `CRITICAL_DEVICE_UNKNOWN` | Пристрій існує у звіті, але його discovery state unknown |
| `DISPLAY_PATH_UNCONFIRMED` | Не підтверджено придатний display/control path |
| `INPUT_PATH_UNCONFIRMED` | Не підтверджено придатний input/control path |
| `NETWORK_PATH_UNTESTED` | Для network-assisted сценарію немає connectivity evidence |
| `OFFLINE_CLOSURE_UNVERIFIED` | Не доведено доступність необхідних локальних deployment artifacts |
| `TARGET_NOT_SELECTED` | Користувач ще не вибрав цільовий диск |
| `TARGET_IDENTITY_STALE` | Target identity змінилася після перегляду/підтвердження |
| `REQUIRED_FIRMWARE_FAILED` | Для потрібної сценарію функції зафіксовано missing/load-error |

Це policy vocabulary для діагностики, а не вимога додати всі коди до schema v1.0.0.

## 8. Синтетичні acceptance cases для #13/#14

| Case | Input condition | Expected result |
| --- | --- | --- |
| A | Report валідний; сценарій local-interactive; display та input підтверджені; target ще не вибраний | Можна показати preflight summary, але не destructive plan |
| B | GPU та DRM connector виявлені, але input class не збирався | `CAPABILITY_NOT_COLLECTED` / unknown; не вигадувати input failure чи readiness |
| C | Display connector connected, active mode є, але користувач не підтвердив читабельність UI | Display detected, usability unconfirmed; local-interactive не ready |
| D | Wi-Fi unknown; сценарій offline; потрібна local software closure підтверджена | Wi-Fi не блокує сценарій |
| E | Ethernet driver bound, але connectivity test не виконувався; сценарій network-assisted | `NETWORK_PATH_UNTESTED`; offline fallback може бути запропонований лише якщо closure підтверджена |
| F | Storage device enumerated, але target не обраний | `TARGET_NOT_SELECTED`; не вибирати диск автоматично |
| G | Target identity змінилася після review | Confirmation invalidated; нуль backend apply calls |
| H | Required runtime firmware = load-error на обов'язковому для сценарію пристрої | Hard-stop для цієї capability; не оголошувати всю систему несумісною |
| I | Firmware package candidate є, runtime load evidence відсутній | Unknown/available-not-confirmed-loaded; не заявляти loaded |
| J | Headless сценарій без перевіреного remote control channel | Unsupported/unknown; мережевий інтерфейс сам по собі недостатній |

Усі unit cases мають використовувати synthetic fixtures і не потребують root, реального hardware, мережі або фізичного диска. QEMU harness #14 перевіряє лише disposable VM із qcow2 та без host block-device passthrough.

## 9. Поточні обмеження

- Schema v1.0.0 не має повного coverage manifest і relationship graph.
- Collector v0.1.0 є inventory-only; він не доводить повну працездатність input, network connectivity, audio, suspend/resume або storage write path.
- USB parent/interface, GPU/connector/monitor та інші відсутні topology edges залишаються unknown до версійованого розширення #18/#5.
- Наявність firmware file/package не доводить успішне runtime завантаження або включення в live image/initrd.
- Поточна policy matrix не є сертифікацією конкретного ПК і не замінює hardware tests #8.

**Висновок:** WSM має відповідати не на абстрактне «чи сумісний цей комп'ютер?», а на точніше питання: «чи достатньо перевірених доказів для цього конкретного способу інсталяції, у цій live-сесії, з цими доступними альтернативами?»

Протоколи перевірки окремих класів сценаріїв: [DISPLAY-COMPATIBILITY.md](testing/DISPLAY-COMPATIBILITY.md), [NETWORK-READINESS.md](testing/NETWORK-READINESS.md), [PCIE-LINK-HEALTH.md](testing/PCIE-LINK-HEALTH.md).
