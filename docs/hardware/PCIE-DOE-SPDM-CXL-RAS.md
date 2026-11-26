# PCIe DOE/SPDM та CXL RAS: межі безпечного preflight

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: дослідницький addendum; не є реалізаційним контрактом
- Критичний шлях: **ні** — дослідження не блокує перший preview-образ
- Дата перевірки upstream ABI: 2026-11-25
- Знімок Linux source: `torvalds/linux` commit `4dce97c6c265544342e716e62fd24bbb232590c5`
- Пов'язана задача: [#81 — PCIe DOE/SPDM authentication та CXL RAS evidence](https://github.com/juv4uk/wsm-desktop/issues/81)
- Межі: лише аналіз ABI та політики доказів; жодних змін schema, collector або installer verdict logic

## Висновок

PCIe DOE/SPDM і CXL RAS можуть дати WSM додаткові **свідчення про можливості платформи та стан надійності**, але їх не можна зводити до одного показника «сумісний / несумісний».

Рекомендується розглядати ці дані як окрему необов'язкову панель `security / reliability`, із суворим read-only allowlist. Виявлення DOE capability не означає успішної автентифікації; наявність TSM не означає, що пристрій уже має активну захищену сесію; CXL security state чи dirty-shutdown counter не є тестом драйвера або функціональної працездатності.

**Preflight не повинен створювати SPDM-сесію, встановлювати PCIe IDE, запускати отримання poison list, scrub, sanitize, erase, firmware update або memory repair.** Усі такі дії залишаються поза автоматичним шляхом інсталятора.

## Джерела та рівень стабільності

Перевірено upstream Linux ABI та реалізацію на зазначеному commit:

- [PCI sysfs ABI](https://github.com/torvalds/linux/blob/4dce97c6c265544342e716e62fd24bbb232590c5/Documentation/ABI/testing/sysfs-bus-pci)
- [TSM class ABI](https://github.com/torvalds/linux/blob/4dce97c6c265544342e716e62fd24bbb232590c5/Documentation/ABI/testing/sysfs-class-tsm)
- [CXL bus ABI](https://github.com/torvalds/linux/blob/4dce97c6c265544342e716e62fd24bbb232590c5/Documentation/ABI/testing/sysfs-bus-cxl)
- [EDAC scrub ABI](https://github.com/torvalds/linux/blob/4dce97c6c265544342e716e62fd24bbb232590c5/Documentation/ABI/testing/sysfs-edac-scrub)
- [EDAC ECS ABI](https://github.com/torvalds/linux/blob/4dce97c6c265544342e716e62fd24bbb232590c5/Documentation/ABI/testing/sysfs-edac-ecs)
- [EDAC memory-repair ABI](https://github.com/torvalds/linux/blob/4dce97c6c265544342e716e62fd24bbb232590c5/Documentation/ABI/testing/sysfs-edac-memory-repair)
- [PCI TSM implementation](https://github.com/torvalds/linux/blob/4dce97c6c265544342e716e62fd24bbb232590c5/drivers/pci/tsm.c)
- [CXL Kconfig](https://github.com/torvalds/linux/blob/4dce97c6c265544342e716e62fd24bbb232590c5/drivers/cxl/Kconfig)
- [Linux ABI testing policy](https://github.com/torvalds/linux/blob/4dce97c6c265544342e716e62fd24bbb232590c5/Documentation/admin-guide/abi-testing.rst)

Каталог `Documentation/ABI/testing` описує інтерфейси, достатньо сформовані для використання, але ще не позначені як стабільні. Вони можуть розширюватися або змінюватися до переходу в `stable`. Тому WSM має фіксувати `uname -r`, версію/конфігурацію ядра та факт наявності конкретних атрибутів у кожному звіті. Наявність атрибута в поточному upstream не гарантує його наявності у вибраному Guix kernel чи в ядрі live-сесії.

## PCIe DOE: discovery — це не authentication

Джерело: `/sys/bus/pci/devices/<BDF>/doe_features/`.

| Спостереження | Семантика upstream | Що це доводить | Чого не доводить |
| --- | --- | --- | --- |
| Каталог `doe_features` | Перелік виявлених DOE features; назва файла — feature, вміст — Vendor ID і Data Object Type | Які DOE feature IDs повідомляє пристрій під час discovery | Автентифікацію, довіру до сертифіката, активну SPDM-сесію або IDE |
| `doe_discovery` | Базова DOE Discovery feature; типовий приклад в ABI — `0001:00` | DOE discovery доступний для читання через PCI sysfs | CMA/SPDM authentication або захищений канал |
| Інші feature-файли | ABI наводить приклади значень для CMA/SPDM та secure CMA/SPDM | Пристрій рекламує відповідні об'єкти DOE | Що платформа має TSM, приймає пристрій чи виконала handshake |

**Правило WSM:** збирати лише назви доступних feature-файлів і нормалізовані пари Vendor ID / Data Object Type, якщо вони потрібні для аналізу. Не трактувати саме discovery як security pass. Сирі DOE exchanges або довільні DOE запити не належать до базового inventory.

## PCIe TSM, SPDM та TDISP

### Динамічне виявлення TSM

- Платформний TSM представляється пристроєм `/sys/class/tsm/tsmN`.
- Його `uevent` сигналізує, що PCI layer може підтримувати встановлення link encryption та інших функцій device security через платформний TSM.
- Каталог `/sys/bus/pci/devices/<BDF>/tsm/` створюється динамічно. PCI ABI прямо вказує: до появи `/sys/class/tsm/tsm0` відсутність `tsm/` не можна вважати доказом відсутності підтримки. Дерево PCI/TSM ще може не завершити enumeration.
- Після завершення TSM enumeration відсутність каталогу може означати, що пристрій не підтримує потрібну комбінацію CMA-SPDM / TDISP або не прийнятий платформним TSM. У звіті все одно потрібно розрізняти `not-enumerated`, `not-exposed` і підтверджене `unsupported`.

### Атрибути та точна семантика

| Атрибут | Доступ upstream | Рекомендація WSM |
| --- | --- | --- |
| `/sys/bus/pci/devices/<BDF>/authenticated` | RO. У реалізації це `DEVICE_ATTR_RO`; коли link TSM керує пристроєм, значення віддзеркалює стан `connect`. Без каталогу `tsm/` воно може відображати native CMA-SPDM auth через kernel certificate store | Дозволити лише читання. Записувати, який саме шлях спостереження застосовний; не трактувати його як незалежний доказ attestation, TDISP binding або працездатності пристрою |
| `tsm/dsm` | RO; повертає PCI-пристрій, який виконує роль Device Security Manager | Необов'язковий локальний контекст; не виводити з нього сертифікат чи успішну перевірку довіри |
| `tsm/bound` | RO; порожнє значення, якщо TDI не bound; інакше назва TSM. Binding запускає VFIO/IOMMUFD після успішного connect | Лише спостереження вже наявного стану. Не запускати bind і не використовувати як preflight requirement |
| `tsm/connect` | RW. Запис назви TSM встановлює зв'язок; зазвичай це SPDM session через PCIe DOE і може також встановити PCIe IDE | **Заборонено записувати** в автоматичному preflight. Це активна операція, а не нешкідливе читання |
| `tsm/disconnect` | WO. Запис розриває сесію | **Ніколи не запускати** з preflight; не від'єднувати вже наявну захищену сесію |

Реалізація Linux на перевіреному commit позначає `authenticated`, `bound` і `dsm` як read-only; `connect` — read/write, `disconnect` — write-only. Це важливе уточнення: назва `authenticated` не означає, що атрибут є командою для запуску автентифікації.

### Окремі докази, а не один «зелений» статус

У майбутній моделі доказів ці поняття мають лишатися окремими:

1. **DOE capability:** пристрій оголосив конкретні DOE feature IDs.
2. **Native authentication state:** kernel повідомляє стан CMA-SPDM, якщо такий шлях експонується.
3. **Platform TSM coordination:** платформний TSM enumerated і пристрій прийнятий для відповідного режиму.
4. **Established link session / IDE:** існує стан connect у TSM; preflight його не створює.
5. **TDISP binding:** окремий стан bound, який пов'язаний із VFIO/IOMMUFD та життєвим циклом TDI.

Жоден із цих пунктів сам по собі не доводить сумісність відео, мережі, звуку, suspend або успішність встановлення WSM.

## CXL: read-only reliability/security evidence

CXL — це окрема категорія для систем із CXL memory devices; вона не є типовою перевіркою звичайної DDR-пам'яті. Нижче наведено тільки атрибути, які потенційно мають сенс для необов'язкової панелі.

| Атрибут | Доступ upstream | Межа доказу |
| --- | --- | --- |
| `memX/firmware_version` | RO | Версія firmware, яку повідомляє CXL memory device; не доводить, що firmware актуальна або безпечна |
| `memX/ram/size`, `memX/pmem/size` | RO | Повідомлена volatile / persistent capacity |
| `memX/numa_node` | RO, якщо платформа має відповідну affinity | NUMA affinity, опублікована ядром; відсутність — не автоматично помилка |
| `memX/security/state` | RO | Поточний security state, зокрема `disabled`, `sanitize`, а для persistent memory — `locked`, `unlocked`, `frozen` |
| `nmemY/cxl/dirty_shutdown` | RO, ABI позначає з kernel v6.15 | Лічильник dirty shutdown, тобто кількість випадків, коли пристрій міг зазнати потенційної втрати даних; значення зберігається після втрати живлення і може переповнюватися |

`dirty_shutdown = 0` — це лише нульове поточне значення лічильника, не сертифікація справності. Відсутній атрибут не можна підміняти нулем: перевірити версію ядра, наявність CXL/NVDIMM bridge та завершеність enumeration. Джерело ABI вказує, що відсутність атрибута означає відсутність необхідної підтримки dirty tracking у відповідному шляху.

## Операції, заборонені автоматичному preflight

Наведені інтерфейси мають побічні ефекти або можуть розкривати чутливі дані. Вони не входять у read-only allowlist.

| Інтерфейс / група | Семантика upstream | Політика WSM |
| --- | --- | --- |
| `memX/trigger_poison_list` | WO; запис `true` витягує з пристрою poison list з адресами та джерелами poison; за ввімкненого tracing формуються kernel events | Не записувати; не збирати й не експортувати адреси/події |
| `memX/security/sanitize` | WO; запускає sanitization user data і metadata пристрою | Не запускати; це destructive operation |
| `memX/security/erase` | WO; secure erase через зміну media encryption keys | Не запускати; це destructive operation |
| `memX/firmware/` | Інтерфейс firmware upload/activation | Не відкривати write path і не оновлювати firmware |
| EDAC `scrubX/addr`, `size` | RW; встановлення адреси/розміру запускає on-demand scrub | Не записувати; не ініціювати scrub |
| EDAC `scrubX/enable_background`, `current_cycle_duration` | RW; вмикає/вимикає patrol scrub або змінює інтервал | Не змінювати фонову активність чи навантаження пам'яті |
| EDAC ECS `mode`, `threshold`, `log_entry_type`, `reset` | RW/WO; змінює режим обліку або скидає ECC counters | Не змінювати параметри й не скидати counters |
| EDAC memory repair `persist_mode`, адресні/координатні поля, `repair` | RW/WO; налаштовує та запускає PPR / sparing / memory repair | Не запускати repair; не змінювати адреси чи режими |

### Чому EDAC інтерфейси можуть бути відсутні

У перевіреному `drivers/cxl/Kconfig`:

- `CXL_EDAC_MEM_FEATURES` залежить від `EXPERT`, `CXL_MEM`, `CXL_FEATURES` та EDAC;
- `CXL_EDAC_SCRUB`, `CXL_EDAC_ECS` і `CXL_EDAC_MEM_REPAIR` — окремі optional options;
- Kconfig прямо описує їх як експертні можливості для керування memory RAS, а не обов'язкову базову функцію.

Отже, відсутність EDAC scrub/repair sysfs tree сама по собі не означає несправність CXL device. Треба відрізняти: kernel option вимкнений, драйвер не завантажений, callbacks не зареєстровані, пристрій не підтримує capability або enumeration ще не завершена. WSM не повинен вмикати `EXPERT` options лише заради preflight і не повинен торкатися їхніх RW/WO control attributes.

## Privacy та експорт звіту

- Не читати й не експортувати `/sys/bus/pci/devices/<BDF>/serial_number` або CXL `memX/serial`: Linux ABI прямо звертає увагу на чутливість serial number.
- Не зберігати й не надсилати raw poison addresses, HPA/DPA coordinates, device event payloads або дампи mailbox/SPDM.
- Не вважати BDF глобально стабільною ідентичністю пристрою; для зовнішньої телеметрії її слід опускати або нормалізувати.
- Локальний звіт може містити достатні для сумісності vendor/device IDs та нормалізовані capability names, але унікальні ідентифікатори мають бути відсутні за замовчуванням.
- Не запускати `lspci -vvv` або сторонній збірний інструмент із припущенням, що він не читає serial/extended capability data; allowlist має бути на рівні джерел і конкретних файлів.

## Рекомендований мінімум для WSM

**Можна розглядати як optional query-only evidence після окремого узгодження schema/collector:**

- наявність і перелік ідентифікаторів `doe_features`;
- стан уже наявного `authenticated` (лише читання, з позначенням native чи TSM path);
- наявність TSM та read-only `dsm` / `bound`, якщо вони вже експонуються;
- CXL `firmware_version`, capacity, NUMA affinity та `security/state`;
- CXL `dirty_shutdown` як окремий reliability counter із версією ядра та контекстом enumeration.

**Не включати до автоматичного preflight:** будь-які записи в sysfs; створення/розрив SPDM session; TDISP bind/unbind; poison list retrieval; scrub/ECS/repair; firmware upload; sanitize/erase; raw serials, poison addresses та чутливі event records.

Для відсутнього або недоступного атрибута використовувати явні стани на кшталт `unknown`, `not-exposed`, `not-enumerated`, `permission-denied` або `not-applicable`. Не перетворювати відсутність атрибута на `unsupported`, `false` або нуль без доказу.

## Нові upstream-розробки: TDX Trusted I/O

16 листопада 2026 року опубліковано [RFC series «TDX: Enable PCIe link encryption for trusted I/O»](https://lists.openwall.net/linux-kernel/2026/11/16/1670). Серія пропонує TDX-host TSM driver, що використовує SPDM через DOE та налаштовує PCIe IDE stream. Автор прямо позначає її як early-review RFC, яка ще не проходила запитаний review x86 maintainers; частина SEAMCALL wrappers на момент листа ще не була опублікована, а CTLV attestation flow перебував у дискусії.

Це перспективний напрям для майбутніх платформ із confidential computing, але **не базова функція WSM і не ознака, що конкретне обладнання вже підтримується**. У цій роботі не інтегрувати RFC-патчі, не вмикати TDX, не запускати TSM connect та не додавати security gate до інсталятора. Повернутися до теми після проходження upstream review/merge та появи відтворюваних platform tests.

## Наступні кроки

1. Передати висновки власникам контракту report schema (#5), collector (#6/#16) і topology (#18).
2. Окремо погодити назви evidence states і privacy allowlist до будь-якої реалізації.
3. Лише після погодження створювати вузькі unit tests на synthetic sysfs fixtures; не потребувати фізичного CXL/TDX обладнання для перевірки заборони запису.
4. Зберігати це дослідження як необов'язковий додаток. Воно не змінює installer verdict і не затримує базову x86_64 desktop-інсталяцію.
