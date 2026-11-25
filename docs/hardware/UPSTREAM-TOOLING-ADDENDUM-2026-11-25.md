# Доповнення до аудиту upstream-інструментів WSM — 25.11.2026

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Батьківська задача: [#4 — аудит апаратних інструментів і джерел](https://github.com/juv4uk/wsm-desktop/issues/4)
- Пов'язані контракти: [#16 — driver/runtime firmware evidence](https://github.com/juv4uk/wsm-desktop/issues/16), [#18 — device topology](https://github.com/juv4uk/wsm-desktop/pull/42), [#20 — display compatibility](https://github.com/juv4uk/wsm-desktop/pull/20), [#25 — network readiness](https://github.com/juv4uk/wsm-desktop/pull/25)
- Це дослідження upstream-можливостей, а не затверджений пакетний маніфест WSM.

## Короткий висновок

WSM варто будувати не навколо одного «детектора сумісності», а навколо кількох незалежних read-only джерел, кожне з яких має вузьку семантику та власне походження доказу. Жоден з інструментів нижче сам по собі не може видати глобальний verdict «комп'ютер сумісний».

## Нові кандидати

| Джерело | Що може додати WSM | Межа доказу | Рекомендована роль |
| --- | --- | --- | --- |
| [hwloc 2.16.0](https://www.open-mpi.org/software/hwloc/v2.16/) | Ієрархія CPU/cache/NUMA/CXL та locality PCI/I/O-пристроїв, включно з окремими accelerator providers; XML topology export | I/O discovery вимкнено за замовчуванням у звичайному API та потребує підтримки ОС; для повного PCI discovery може знадобитися libpciaccess. Не описує USB interface binding або GPU→DRM connector→monitor | Опційний provider для CPU↔NUMA↔PCI locality, не заміна зв'язків #18 |
| [libdisplay-info 0.4.0](https://gitlab.freedesktop.org/emersion/libdisplay-info) | EDID/DisplayID decode; реліз додав DisplayID v1 Type IV timings та DisplayID v2 CTA-861 blocks | Advertised timing не є KMS-exposed mode, active mode або functional pass. High-level API краще ізолює споживача від змін low-level API | Опційний parser у display lane поруч із kernel DRM/KMS observations |
| [drm_info 2.10.0](https://gitlab.freedesktop.org/emersion/drm_info) | Локальний DRM device/property inventory, JSON output через `drm_info -j` | JSON може містити GPU/monitor identifiers; output/version contract треба pin-ити. Не доводить, що режим реально працює або що монітор фізично підключений до конкретного GPU без явного topology edge | Опційний локальний DRM provider; без upload у DRM database |
| [systemd hwdb 262](https://www.freedesktop.org/software/systemd/man/262/hwdb.html) | Локальне зіставлення modalias-подібних ключів із udev property/value metadata; підтримує окремий query шлях | Нормалізація назви/властивостей не доводить driver binding, runtime firmware load чи роботу пристрою | Допоміжний шар назв і quirks, не compatibility oracle |
| [PCIe AER sysfs counters](https://github.com/torvalds/linux/blob/master/Documentation/ABI/testing/sysfs-bus-pci-devices-aer) | Correctable, non-fatal та fatal PCIe error counters для AER-capable пристроїв: `aer_dev_correctable`, `aer_dev_nonfatal`, `aer_dev_fatal` і root-port totals | Лічильники означають помилки «as seen/reported» відповідним компонентом. Endpoint-проблема може інкрементувати link partner/root port, а endpoint — показувати нуль. Відсутність файла не означає нуль | Додаткове read-only спостереження про PCIe link/error history з BDF джерела та timestamp |
| [devlink health](https://docs.kernel.org/6.19/networking/devlink/devlink-health.html) | `devlink health show` може показати status/config зареєстрованих драйвером health reporters для NIC/switch/accelerator | Покриття залежить від драйвера. `diagnose` викликає driver callback і має admin-only netlink permission; `dump show` може згенерувати новий dump; `recover`, `test`, `set`, `dump clear` не є пасивними | Лише опційний status query через `show`; інші команди — окремий consent-based support mode |
| [VKMS](https://docs.kernel.org/gpu/vkms.html) + [IGT GPU Tools](https://gitlab.freedesktop.org/drm/igt-gpu-tools) | Віртуальний DRM/KMS display для headless CI/VM перевірок | Для VKMS потрібно завантажити модуль/налаштувати configfs; IGT може вимагати окремої сесії без compositor-а. Це змінює стан тестового kernel і не є live preflight | Ізольована CI/VM lane, не probe на фізичному ПК |
| [fwupd HSI](https://fwupd.github.io/hsi.html) | Окремі показники firmware/platform security posture | Security posture не доводить наявність runtime firmware blob, успішне виконання `request_firmware()` чи ініціалізацію пристрою | Окремий security report; не змішувати з #16 compatibility evidence |

## Додаткові hardware providers: AMD SMI та CXL sysfs

### AMD SMI — окремий accelerator provider

AMD SMI є наступником ROCm SMI та надає API для GPU/device management, telemetry і topology. Офіційна документація 27.2.0 підтверджує підтримку Linux bare metal та Linux VM guests; WSL2 позначено як experimental. Для побудови WSM adapter-а:

- Віддати перевагу Python або C++ API. AMD прямо позначає CLI як приклад для розробки telemetry tools і рекомендує бібліотечний API як надійніше джерело даних.
- За наявності AMD GPU та завантаженого `amdgpu` драйвера optional topology provider може повідомляти GPU↔GPU access, abstracted hop/weight, link type, NUMA bandwidth та P2P capabilities (coherency, atomics, DMA, bidirectional).
- JSON output CLI може бути зручним для експериментів, але не є стабільним WSM report schema. Adapter має бути version-pinned і тримати окремо vendor-native observations та report-local device IDs.
- AMD SMI — telemetry/topology evidence, не доказ сумісності для boot або display path. Відсутність AMD SMI/ROCm не означає несумісність AMD GPU; цей provider не повинен бути обов'язковим preflight dependency.
- Не викликати mutating CLI commands на етапі inventory: документація CLI також містить `set` та `reset`. Використовувати тільки окремо reviewed read-only queries; telemetry values можуть змінюватися в часі й не є статичними hardware identity.
- У ROCm 10.2.0 (2026-11-18) AMD SMI 27.2.0 додав єдиний `amdsmi_get_link_topology()` API для bare metal: link weight/status/type, hop count і framebuffer-sharing data; він має Python та Rust bindings. У тій самій версії опубліковано Python library `amdsmi` 27.2.0 на PyPI без вимоги встановлювати весь ROCm SDK, але залишаються вимоги Linux x86_64, glibc ≥ 2.27, драйвера `amdgpu` та `libdrm`. Це потенційний спосіб окремо пакувати optional provider, а не підстава для `pip install` або мережевого встановлення під час preflight.

Для `amdsmi_get_link_topology()` не перетворювати поля на прості verdict-и:
- `num_hops` — абстрактні кроки топології (обмежені 255), а не кількість фізичних xGMI links;
- `link_status` описує API status enum, але AMD окремо застерігає, що це **не link-health і не P2P-access status**; успішні bare-metal виклики наразі можуть повертати `ENABLED` навіть коли CLI перевірка доступності P2P дає інший результат;
- `fb_sharing = 0` означає «недоступний або запит не вдався», тому не можна записувати це як доведене `P2P=false` без додаткового статусу/причини;
- API виконує послідовні запити, тому результати різних пар можуть належати до трохи різних моментів часу; зберігати timestamp кожного спостереження або спільний короткий collection window;
- `amdsmi_init()` за замовчуванням ініціалізує GPU. CPU initialization — окрема опція й потребує `amd_hsmp` та HSMP, увімкненого в BIOS; за відсутності цього шляху не позначати AMD GPU provider як failed і не робити CPU telemetry обов'язковою.

Джерело точних полів та обмежень: [AMD SMI 27.2.0 Python API reference](https://rocm.docs.amd.com/projects/amdsmi/en/docs-10.2.0/reference/amdsmi-py-api.html), функція `amdsmi_get_link_topology` і розділ `amdsmi_init`.

Джерела: [AMD SMI 27.2.0, документація ROCm 10.2.0](https://rocm.docs.amd.com/projects/amdsmi/en/docs-10.2.0/), [AMD SMI CLI guidance 27.2.0](https://rocm.docs.amd.com/projects/amdsmi/en/docs-10.2.0/how-to/amdsmi-cli-tool.html), [AMD SMI topology output 27.2.0](https://rocm.docs.amd.com/projects/amdsmi/en/docs-10.2.0/how-to/amdsmi-cli-tool.html#amd-smi-topology).

### CXL sysfs — типізована fabric topology та memory locality

Linux kernel експонує CXL fabric у `/sys/bus/cxl/devices/`: root/port/endpoint objects, decoders, memory devices (`memX`), regions і DAX regions. Це важливий майбутній source для workstation/server-class memory topology, яку плоский PCI inventory не описує.

Корисні read-only observations, якщо CXL subsystem присутній:
- `devtype`, `uport`, `parent_dport`, downstream port links і декодери для відтворення root→host bridge/switch→endpoint path;
- decoder `start`, `size`, `target_list`, `interleave_ways`, `interleave_granularity`, `mode` (лише читання значення; не писати в атрибут);
- `memX/numa_node`, `ram/size`, `pmem/size`, `firmware_version`, `security/state` там, де вони наявні;
- endpoint `CDAT` як read-only capability/latency-bandwidth metadata source, якщо DOE mailbox та CDAT read доступні.

**Критична межа relationship inference:** kernel CXL driver documentation прямо зазначає, що endpoint є логічним port object і один physical memory device може представляти кілька endpoints; відповідність endpoint↔memdev не гарантується окремим sysfs relationship. Якщо немає прямого kernel-provided link, WSM має лишати ребро unknown, не з'єднувати за близькістю, однаковою назвою чи порядком enumeration.

Не торкатися writable/side-effecting CXL controls під час preflight: зокрема `/sys/bus/cxl/flush`, decoder mode/target configuration, unbind/reset, `cxl create`, `cxl set` або подібних операцій. Для v1 це read-only snapshot із provenance, не memory reconfiguration чи security attestation.

Джерела: [Linux CXL Driver Operation](https://www.kernel.org/doc/html/latest/driver-api/cxl/linux/cxl-driver.html), [Linux CXL Driver Theory of Operation](https://origin.kernel.org/doc/html/latest/driver-api/cxl/theory-of-operation.html), [Linux 6.19 CXL sysfs ABI](https://www.kernel.org/doc/html/v6.19/admin-guide/abi-testing.html).

## Детальні межі hwloc I/O locality

Офіційна документація hwloc 2.16.0 уточнює кілька важливих умов, які мають бути явними в WSM adapter-і:

- **I/O discovery не активується типовим API за замовчуванням.** Його потрібно явно вмикати до завантаження topology, наприклад через `HWLOC_TYPE_FILTER_KEEP_IMPORTANT` або точковий filter для потрібних типів. Не вмикати `KEEP_ALL` автоматично в preflight лише заради «повнішого» звіту.
- **Фактична locality I/O зараз визначається тільки на Linux.** На інших ОС hwloc поміщає I/O devices під кореневий topology object, що не є реальною NUMA locality.
- **Повніше PCI/bridge discovery залежить від libpciaccess.** Без нього Linux може побачити частину PCI topology, але втратити назви пристроїв/bridge-ів; частина платформ може вимагати привілеїв для певних probing-операцій. WSM не має підвищувати привілеї лише для hwloc.
- **I/O object не несе власних CPU/node sets.** Їхні CPU/node sets є NULL; locality потрібно отримувати проходом до найближчого non-I/O ancestor у topology tree. Не трактувати CPU set самого PCI/OS node як відомий.
- **PCI function і software handle не обов'язково відображаються 1:1.** Один PCI device може породити кілька OS-device handles (наприклад, HCA та кілька інтерфейсів), а PCI graphics device може не мати доступного software handle; DRM `card0`/ `renderD128` у Linux component за замовчуванням filtered out як non-important.
- **Vendor accelerator backends — окремий optional layer.** NVML/RSMI/OpenCL/Level Zero можуть надати додаткові GPU/software device handles, але їхня доступність залежить від build flags і runtime libraries. Не запускати `lstopo` з широким default probing як безумовний preflight: документовані компоненти можуть пробуджувати GPU, ініціалізувати vendor runtime або виконувати додаткові звернення. Використовувати мінімальний explicit filter, фіксувати backend/version і пропускати provider, якщо його безпечність не підтверджена.

Практичний висновок: WSM спершу збирає основні report-local identity/relationship факти через sysfs/DRM/udev; hwloc може доповнити тільки підтверджену CPU↔NUMA↔PCI locality. Його object tree не замінює schema #18 і не може самостійно встановити GPU→connector→display, USB composite interface binding або реальне фізичне підключення.

Джерело: [hwloc 2.16.0 I/O Devices documentation](https://www.open-mpi.org/projects/hwloc/doc/v2.16.0/iodevices.html), зокрема розділи *Enabling and requirements*, *OS devices*, *Consulting I/O devices and binding*; [hwloc 2.16.0 FAQ](https://www.open-mpi.org/projects/hwloc/doc/v2.16.0/faq.html) — особливості lstopo та optional GPU runtimes.

## Додаткове оновлення: PCIe DOE/SPDM та CXL RAS

### PCIe DOE, CMA-SPDM, TDISP та IDE

Linux PCI sysfs тепер може експонувати directory `doe_features` для пристроїв із PCIe Data Object Exchange (DOE). Обов'язковий `doe_discovery` feature має значення `0001:00`; якщо пристрій підтримує CMA/SPDM та secure CMA/SPDM, документація наводить додаткові feature IDs `0001:01` і `0001:02`. Це **capability discovery**, не доказ успішної автентифікації.

Окремий security state може з'являтися в `/sys/bus/pci/devices/<BDF>/tsm/` лише якщо фізична function підтримує CMA-SPDM authentication і TDISP та прийнята platform TSM driver-ом. Directory з'являється динамічно після завантаження TSM driver; до появи `/sys/class/tsm/tsm0` відсутність `tsm/` не можна трактувати як unsupported.

Ключові attributes мають різні семантики:

| Attribute | Семантика | Межа / preflight rule |
| --- | --- | --- |
| `doe_features/*` | Список DOE feature IDs, які device повідомляє як підтримувані | Capability only; не означає, що SPDM session встановлено |
| `tsm/connect` | RW: створює TSM connection; зазвичай встановлює SPDM over PCIe DOE і може встановити PCIe IDE | **Ніколи не писати** в автоматичному preflight |
| `tsm/disconnect` | WO: розриває TSM connection | Не викликати в preflight |
| `tsm/dsm` | RO: назва Device Security Manager; у connected state свідчить про secure-session connection | Можна читати лише як уже наявне state, без connect/disconnect |
| `tsm/bound` | RO: TSM binding для TDISP operational states LOCKED/RUN/ERROR | Це security/virtualization state, не функціональна перевірка пристрою |
| `authenticated` | Native CMA-SPDM authentication status, або alias до TSM connect state, коли `tsm/` присутня | Вміст залежить від режиму TSM; reauthentication через запис не запускати |

Не змішувати DOE feature IDs, authentication outcome, TDISP binding, IDE link encryption, driver binding та звичайну runtime functionality. Якщо TSM ще не завантажився або sysfs status недоступний — `unknown/not-collected`, не `unauthenticated`.

PCIe SPDM authentication належить до окремої security pane. Вона не доводить, що Linux драйвер завантажено, runtime firmware blob присутній/застосований, пристрій ініціалізовано або його функція сумісна з installer-ом. Невдала authentication також не повинна непомітно змінювати драйвер binding чи запускати автоматичний unbind/remove policy у WSM.

### CXL memory device RAS та security

Linux CXL sysfs надає кілька потенційних read-only спостережень для CXL memory devices/regions. Це не загальна функція звичайного ПК без CXL hardware; provider має бути optional і працювати лише коли kernel експонує відповідні об'єкти.

| Attribute | ABI semantics | WSM interpretation |
| --- | --- | --- |
| `memX/firmware_version` | RO: firmware revision із Identify Memory Device output | Версія, заявлена CXL device; не доказ оновлення або успішної runtime driver firmware request |
| `memX/ram/size`, `memX/pmem/size` | RO: volatile та persistent capacity | Capacity evidence, не compatibility verdict |
| `memX/numa_node` | RO: CPU NUMA affinity, коли платформа її визначила | Допоміжний topology/locality факт, якщо він доступний |
| `memX/security/state` | RO: CXL security state (`disabled`, `sanitize`, а для persistent memory також `locked`/`unlocked`/`frozen`) | Security state; `sanitize` — спостереження процесу, не дозвіл його запускати |
| `memX/trigger_poison_list` | WO: write `true` просить driver зчитати poison list з пристрою | **Не запускати** автоматично; це operation-triggering retrieval, не пасивний read |
| `nvdimm-bridge0/ndbusX/nmemY/cxl/dirty_shutdown` | RO: persistent count можливих data-loss dirty shutdown events; counter зберігається через power loss та може wrap | Історичний risk signal із provenance; ненульове значення не локалізує причину, нуль/відсутність не гарантує цілісність |
| EDAC scrub controls | Unified sysfs controls абстрагують CXL patrol scrub, CXL ECS, ACPI RAS2/ARS та інші scrubbers | Для preflight не змінювати scrub rates і не запускати on-demand scrub; capability queries потребують окремого exact-ABI review |

Особливо важливо: `trigger_poison_list` є write-only, отже його не можна сприймати як read-only спосіб дізнатися, чи є poison. Не використовувати `sanitize`, `region/commit`, scrub-rate settings, on-demand scrub або repair controls у hardware preflight. Якщо poison/error records уже наявні в kernel event stream, їх можна аналізувати за окремим privacy/redaction policy; не створювати новий device query автоматично.

### Категорії evidence

- **Capability**: пристрій повідомляє, що має DOE feature або CXL capability.
- **Security state**: kernel/TSM звітує про authentication, secure-session або TDISP state.
- **Reliability history**: dirty-shutdown/poison/error record уже був зафіксований.
- **Runtime driver evidence**: окремо підтверджує driver binding та firmware request semantics.
- **Functional evidence**: доводить роботу конкретної функції в тестовому сценарії.

Жодна з цих категорій не підміняє іншу. Зберігати source BDF/report-local ID, точний attribute, час/boot session і versioned provider; не експортувати PCI/CXL serials або raw memory addresses за замовчуванням.

Джерела:
- [Linux PCI sysfs ABI: DOE features, TSM, SPDM and TDISP](https://github.com/torvalds/linux/blob/master/Documentation/ABI/testing/sysfs-bus-pci) — у поточному upstream описані `doe_features`, `tsm/connect`, `tsm/dsm`, `tsm/bound` та `authenticated` semantics.
- [Linux CXL sysfs ABI](https://gbmc.googlesource.com/linux/+/e003ef2cb1de41edda508ea1fdb21974f9f18dfb/Documentation/ABI/testing/sysfs-bus-cxl) — firmware_version, capacity, NUMA, security state, poison-list trigger, QoS, dirty-shutdown count.
- [Linux EDAC scrub control](https://docs.kernel.org/edac/scrub.html) — CXL patrol scrub/ECS та інші scrub capabilities; частина operations змінює scrub policy або запускає роботу.
- [PCI CMA/SPDM sysfs RFC history](https://lkml.iu.edu/hypermail/linux/kernel/2602.1/03817.html) — authentication state та повторна автентифікація через write; WSM preflight не повинен запускати reauthentication.

## Правила інтеграції

### PCIe AER

- Читати тільки наявні AER sysfs attributes; нічого не записувати до ratelimit/config файлів.
- Зберігати BDF того об'єкта, на якому фактично прочитано counter. Не переносити його на endpoint/link partner за здогадом.
- Розділяти correctable, non-fatal і fatal counters; вони мають різний вплив на link/function.
- Відсутній attribute або недоступний sysfs — `unknown/not-collected`, не нуль.
- Значення — накопичені counters у контексті поточного драйвера/boot. Самі по собі вони не доводять поточну несправність і не замінюють функціональний тест.

Офіційний [PCIe AER guide](https://www.kernel.org/doc/html/latest/PCI/pcieaer-howto.html) пояснює, що correctable errors можуть бути автоматично виправлені апаратурою, тоді як uncorrectable fatal errors можуть зробити link ненадійним і запускати recovery. Для installer-а це має бути обережний diagnostic signal, а не негайна загальна заборона інсталяції.

### devlink health

- `devlink health show` — лише запит статусу/конфігурації reporter-ів, якщо команда та driver support доступні.
- Не запускати `recover`, `test`, `set` або `dump clear` у preflight.
- Не запускати `diagnose` чи `dump show` автоматично: драйвер callback може виконувати додатковий збір даних, а dump може створюватися за відсутності збереженого.
- Відсутність reporter-а означає `not-collected/unsupported-by-provider`, а не «пристрій здоровий».

### Display stack

#### Безпека DisplayID parser-а

EDID/DisplayID надходить від зовнішнього пристрою або з локального файла й має трактуватися як недовірений вхід. Для `libdisplay-info` оприлюднено два дефекти читання за межами buffer у DisplayID parser-ах:

- [CVE-2026-112271](https://access.redhat.com/security/cve/cve-2026-112271) — DisplayID v1 parser може читати за межами секції, коли оголошена довжина data block перевищує її межі.
- [CVE-2026-112272](https://access.redhat.com/security/cve/cve-2026-112272) — аналогічна помилка у parser DisplayID v2; Red Hat зазначає, що його RHEL-релізи не уражені, оскільки shipped packages не містять уразливої parser logic.

Публічні записи для upstream `libdisplay-info` вказують на вразливий код у версіях **through 0.4.0** ([112271](https://explore.alas.aws.amazon.com/CVE-2026-112271.html), [112272](https://explore.alas.aws.amazon.com/CVE-2026-112272.html)). Це не означає, що кожен downstream package з рядком версії `0.4.0` обов'язково уражений: vendor може вилучити DisplayID parser logic або backport-ити виправлення. Визначати affectedness треба за точним source/package revision та фактичним вмістом parser-а, а не лише за version string.

Стан конкретних vendor advisory перевірено **2026-11-25**:
- AWS ALAS для [CVE-2026-112271](https://explore.alas.aws.amazon.com/CVE-2026-112271.html) позначає `libdisplay-info` у Amazon Linux 2023 та Amazon Linux 2027 Preview як **Pending Fix**.
- AWS ALAS для [CVE-2026-112272](https://explore.alas.aws.amazon.com/CVE-2026-112272.html) позначає ті самі downstream packages як **Not Affected**.
- Для CVE-2026-112272 Red Hat окремо вказує, що RHEL releases не уражені, оскільки shipped packages не містять vulnerable DisplayID parser logic: [Red Hat advisory](https://access.redhat.com/security/cve/cve-2026-112272).

Ці vendor statuses не суперечать upstream affected range: вони описують конкретні downstream package contents/patches. WSM має оцінювати саме джерельну ревізію та наявність vulnerable parser logic, а не переносити статус одного дистрибутива на інший.

**Правило для WSM:** не додавати `libdisplay-info 0.4.0` як обов'язковий parser до privileged/live preflight. EDID/DisplayID parsing лишається optional і не запускається з підвищеними привілеями; перед його використанням перевіряти точну upstream/downstream revision на наявність відповідних виправлень. За відсутності такої перевірки використовувати read-only DRM/KMS properties, а parser-specific fields залишати `unknown/not-collected`. Спеціально сформований EDID слід вважати untrusted input.


- Користуватися kernel DRM/KMS connector properties та active state як окремими джерелами.
- `drm_info -j` та libdisplay-info — додаткові provider-и, output яких треба прив'язувати до exact tool version.
- Не з'єднувати GPU і connector за іменем/порядком. Потрібен явний report-local relationship з provenance від #18.
- Не вважати EDID/DisplayID advertised timings функціонально перевіреними режимами.

## Guix System VM: актуальні upstream зміни

У Guix upstream 2026-11-14 були злиті дві зміни, які слід врахувати під час bring-up WSM:

- Commit `42d2543dd2985a904ab5f16a1c8b2abb354aa923` змінює `guix system vm`, щоб launcher і disk image використовували ту саму OS derivation після трансформацій image (зокрема UUID assignment). Це усуває ситуацію, коли VM могла посилатися на відмінну derivation від тієї, що зареєстрована всередині образу.
- Commit `528ba9a3069a8767506f1fe6b7badeeb57a02542` додає writable store у VM за замовчуванням; раніше VM із shared read-only store не дозволяла запускати `guix-daemon` і виконувати Guix build усередині guest.

Ці зміни не є доказом, що їх містить поточний WSM Guix environment. Перевіряти їх на фактичному `guix describe`/автентифікованому channel snapshot після #39. Для базового boot smoke достатньо перевірити досягнення guest console; окремим наступним тестом можна перевірити writable store і запуск `guix-daemon` усередині VM.

Джерела: [Guix VM: single operating-system derivation](https://www.mail-archive.com/guix-commits%40gnu.org/msg405644.html), [Guix VM: writable store by default](https://www.mail-archive.com/guix-commits%40gnu.org/msg405638.html).

## QEMU як окремий інструмент CI/VM-перевірок

QEMU не є hardware-discovery provider і не має бути обов'язковою залежністю live preflight. Це контрольоване середовище для integration tests:

- Офіційна сторінка QEMU на 25.11.2026 показує **11.1.3** (28.10.2026) як останній stable release та **11.2.0-rc1** (18.11.2026) як новіший release candidate. Для основної CI-матриці залишати stable-версію, яку надає runner/package source; RC перевіряти лише в окремому compatibility job після закріплення checksum/version.
- Наш synthetic ISO test перевіряє саме harness, serial marker і відсутність host passthrough. Він не замінює Guix System build/boot або виконання `wsm-install` усередині Guix guest.
- Перед порівнянням результатів потрібно фіксувати точну версію QEMU, machine type, firmware/BIOS, kernel/initramfs, CPU model та acceleration mode (TCG/KVM). Не змішувати TCG з KVM результати як однакову платформу.
- Для disposable install tests використовувати тільки тимчасовий qcow2, no-network за замовчуванням, без host block-device/USB/GPU passthrough і без EFI variable store.

Upstream: [QEMU downloads and releases](https://www.qemu.org/download/), [QEMU 11.0 release notes](https://www.qemu.org/2026/04/22/qemu-11-0-0/). Статус 11.2.0-rc1 не означає, що його вже слід ставити у звичайний CI runner.

## Packaging та відтворюваність

Цей список не підтверджує, що будь-який пакунок уже присутній у WSM live image або у Guix/Nix closure.

Після появи перевіреного `channels.lock.scm` у #39 треба для кожного кандидата записати:
1. точну pinned revision Nixpkgs або Guix;
2. package attribute/name і version;
3. license metadata;
4. результат evaluation;
5. substitute availability окремо від локального build;
6. dependency/closure size, якщо доступний;
7. чи тестувався tool runtime в live image/VM.

Не додавати Nonguix, nonfree firmware, substitute keys або нові binary caches як побічний ефект цього аудиту. Підтримувати free-only baseline і optional compatibility profile окремо.

## Джерела

- [hwloc v2.16.0 stable release](https://www.open-mpi.org/software/hwloc/v2.16/) — стабільний реліз від 2026-11-19 за офіційною таблицею завантажень Open MPI; SHA-256 для tar.bz2: ad05eb466b915a4f0e0228173d7e09974ac38760c38d5b6f060254c050fca12d.
- [hwloc I/O device documentation](https://hwloc.gitlabpages.inria.fr/doc-snapshots/v2.x-html/a00369.html) — фільтри I/O discovery та залежність від підтримки ОС/libpciaccess.
- [libdisplay-info 0.4.0 release announcement](https://mail-archive.com/wayland-devel%40lists.freedesktop.org/msg44365.html) — DisplayID v1/v2 coverage та API compatibility notes.
- [drm_info 2.10.0 package record](https://openmamba.org/en/rpms/base/drm_info/) — version, MIT license та build requirements; upstream source вище.
- [systemd hwdb 262 manual](https://www.freedesktop.org/software/systemd/man/262/hwdb.html) — modalias-like mapping і query semantics.
- [Linux PCIe AER sysfs ABI](https://github.com/torvalds/linux/blob/master/Documentation/ABI/testing/sysfs-bus-pci-devices-aer) та [AER implementation](https://github.com/torvalds/linux/blob/master/drivers/pci/pcie/aer.c).
- [Linux devlink health](https://docs.kernel.org/6.19/networking/devlink/devlink-health.html), [netlink specification](https://docs.kernel.org/netlink/specs/devlink.html), [devlink-health(8)](https://manpages.debian.org/unstable/iproute2/devlink-health.8.en.html).
- [Linux VKMS](https://docs.kernel.org/gpu/vkms.html) — software-only KMS testing in isolated VM/CI.
- [fwupd HSI](https://fwupd.github.io/hsi.html) — platform security posture, a separate evidence category.

## Додаткові спостереження щодо Guix packaging

Ці факти не доводять, що відповідні пакунки входять до WSM closure: точний висновок можливий лише після появи перевіреного channels.lock.scm у #39.

- У Guix upstream було знайдено оновлення пакунка hwloc до **2.15.0** у гілці world-rebuild (commit від 23.09.2026). В окремому наступному commit тієї ж гілки прибрано libdrm, rocm-smi-lib, --enable-rsmi та --with-rocm через проблеми лінкування з різними GCC. Це важливе обмеження: навіть наявність hwloc у Guix не гарантує AMD ROCm-SMI GPU-locality provider. Це branch-scoped upstream evidence, а не твердження про будь-який невідомий pinned WSM channel. Джерела: [Guix hwloc 2.15.0 update](https://www.mail-archive.com/guix-commits%40gnu.org/msg394298.html), [Guix removal of ROCm-SMI/libdrm inputs](https://www.mail-archive.com/guix-commits%40gnu.org/msg394603.html).
- У GNU Guix з'явився native fwupd-service-type для системного сервісу fwupd. Його варто розглядати як окрему optional firmware-management/security capability, а не як заміну read-only runtime firmware evidence з #16. Джерело: [Guix fwupd-service-type commit](https://www.mail-archive.com/guix-commits%40gnu.org/msg356181.html).
- libdisplay-info вже фігурує як dependency у Guix-описах графічного стеку (наприклад, Weston/Mutter), але це не доводить окремий user-facing CLI provider у мінімальному WSM образі. drm_info і далі треба перевіряти як окремий package attribute у точній locked revision.
- hw-probe знайдено як пакет стороннього каналу Guixrus, не як підтверджену частину офіційного default channel. Його звичний -upload workflow несумісний із локальною privacy-first межею WSM без явної згоди користувача. Джерело: [Guixrus hw-probe package listing](https://toys.whereis.social/?channel=guixrus&page=12&search=).

## Висновок

Першими для реального WSM експерименту варто оцінити `libdisplay-info 0.4.0`, `drm_info 2.10.0`, `hwloc 2.16.0` (стабільний upstream-реліз від 2026-11-19; доцільно почати з ізольованого provider-прототипу) та read-only PCIe AER counters. Наявність hwloc 2.16.0 у точному Guix/Nix closure WSM ще не доведена; її треба перевірити після автентифікованого `channels.lock.scm` у #39. `devlink health show` — optional support for selected NIC/accelerator drivers. VKMS/IGT — тільки CI/VM. fwupd HSI — окремий security pane.

Ні один із цих інструментів не повинен самостійно виставляти загальний verdict сумісності. WSM має зберігати первинний факт, джерело, час, обмеження та невідомі стани окремо від policy decision.
