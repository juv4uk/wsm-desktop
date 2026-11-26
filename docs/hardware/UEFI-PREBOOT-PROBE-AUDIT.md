# Аудит безпечного UEFI pre-boot provider

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Статус: дослідницький протокол, не реалізація EFI application і не дозвіл змінювати report schema.
Критичний шлях: **ні** — дослідження не блокує перший preview-образ.
Дата: 2026-11-25. Задача: [#92](https://github.com/juv4uk/wsm-desktop/issues/92).

## Рішення

Не переносити wsm-os/probe/handoff-probe.c у WSM Desktop як готовий preflight-компонент. Це корисний дослідницький UEFI-зразок, але він збирає зайвий execution state, друкує фізичні адреси та виконує WRMSR під час читання microcode revision.

Рекомендований напрям — окремий мінімальний UEFI application із вузьким allowlist. Він доповнює Linux/sysfs collector, але не замінює докази про driver binding, runtime firmware, DRM/KMS або функціональну працездатність.

Цей аудит не додає EFI binary, не змінює hardware-report schema v1.0.0 і не виконує firmware/host operations.

## Походження та повторне використання

У juv4uk/wsm-os знайдено:
- probe/handoff-probe.c — UEFI application, що читає стан до ExitBootServices();
- probe/build.sh — Clang target x86_64-unknown-windows та lld-link, заголовки gnu-efi без runtime-бібліотеки;
- probe/README.md — межі handoff, exit-boundary та physical-boot probes.

SHA у issue #92 не резолвиться: 12b36c0d17e13b8cd2bb7999f82ac2511d30ea8e повертає 404 від GitHub API. Фактична історія файла:
| Commit | Зміна |
| --- | --- |
| [477dad9c9dd9731a94707168f72e2271b9919fd5](https://github.com/juv4uk/wsm-os/commit/477dad9c9dd9731a94707168f72e2271b9919fd5) | Початковий live UEFI handoff probe |
| [ab194e332ddecf06ff1b28b8cb88f1c30de25ba9](https://github.com/juv4uk/wsm-os/commit/ab194e332ddecf06ff1b28b8cb88f1c30de25ba9) | Додано вимірювання TSC парою читань |

Джерела: [handoff-probe.c](https://github.com/juv4uk/wsm-os/blob/main/probe/handoff-probe.c), [probe README](https://github.com/juv4uk/wsm-os/blob/main/probe/README.md), [build.sh](https://github.com/juv4uk/wsm-os/blob/main/probe/build.sh).

### Ліцензійна межа

wsm-os має власну текстову ліцензію «ВОЛЬНІСТЬ». У перевіреному handoff-probe.c немає окремого SPDX-ідентифікатора або file-level grant, але обидва репозиторії належать тому самому правовласнику й поширюються під однією ліцензією — [LICENSING.md](../../docs/LICENSING.md). Тому питання сумісності ліцензій між wsm-os і WSM Desktop знято; лишається технічне рішення, чи варто взагалі переносити цей probe (див. висновок вище).

Цей аудит не копіює вихідний код. Для майбутньої реалізації потрібне явне уточнення/дозвіл правовласника або незалежна clean-room реалізація за публічною UEFI Specification. Не робити висновок про несумісність ліцензій без окремого правового рішення.

### Параметри QEMU machine profile з wsm-os-lisp

Для тестового harness доречно повторно використати параметри [machine profile](https://github.com/juv4uk/wsm-os-lisp/blob/main/contracts/qemu-m0-machine-profile.lisp): x86_64, q35, OVMF, 128 MiB RAM, COM1 115200 8N1, display off, reboot disabled, timeout 30 секунд. Цей файл описує конфігурацію тестового середовища; він **не містить OVMF firmware image, готового disk fixture чи snapshot**. Сам firmware binary має походити з окремо визначеного та зафіксованого пакета/джерела harness. Ці параметри не є production machine profile або WSM schema. Результат такого запуску має provenance `qemu-ovmf`, не `physical-uefi`.

## Аудит наявного probe

| Наявна дія/поле | Межа | Рішення WSM |
| --- | --- | --- |
| CPUID vendor/family/model/stepping | У QEMU описує емульовану CPU model | Дозволити з provenance |
| APIC ID | Зайва ідентифікаційна деталь | Не збирати |
| CR0/CR3/CR4, EFER, RSP/RFLAGS, GDTR/IDTR | Внутрішній execution state та адреси | Не збирати |
| Довільні MSR reads | Непотрібні inventory; залежать від CPU/platform | Не збирати |
| write_msr(0x8B, 0) перед CPUID для IA32_BIOS_SIGN_ID | Виконує WRMSR | Не включати у strict read-only v1 |
| TSC RDTSC до/після Stall | Таймінг, не доказ сумісності | Не збирати |
| GetMemoryMap aggregate counts | Snapshot до ExitBootServices; allocation може змінити map | Лише агрегати за типами |
| ACPI RSDP / SMBIOS presence | Не доводить валідність таблиць | Тільки boolean presence |
| GOP current mode | Firmware graphics handoff | Роздільність, pixel format, pixels-per-scanline |
| GOP FrameBufferBase | Фізична адреса | Не виводити й не серіалізувати |

### Microcode: точне формулювання

read_live_microcode_revision() записує нуль у MSR IA32_BIOS_SIGN_ID (0x8B), викликає CPUID(1), потім читає MSR. Intel SDM описує це як архітектурну процедуру отримання signature поточного microcode; це не завантаження нового microcode через IA32_BIOS_UPDT_TRIG. Водночас регістр має доступ R/W і helper виконує WRMSR. За правилом WSM «preflight не змінює апаратний стан» цей показник відкладається з першої версії.

Джерела: [Intel SDM Vol. 3A, §12.11.7](https://cdrdv2-public.intel.com/874240/325462-090-sdm-vol-1-2abcd-3abcd-4.pdf), [Intel SDM Vol. 4 — IA32_BIOS_SIGN_ID](https://cdrdv2-public.intel.com/774500/335592-sdm-vol-4.pdf).

## Рекомендований allowlist

Мінімальний незалежний UEFI application може збирати:
1. Execution provenance: qemu-ovmf або physical-uefi, встановлений тільки за фактичним способом запуску.
2. CPUID: vendor, normalized family/model/stepping; без APIC ID та унікальних CPU identifiers.
3. UEFI protocol presence: факт запуску UEFI application, GOP, ACPI RSDP entry та SMBIOS entry; EFI variables не читати.
4. GOP current mode: horizontal/vertical resolution, PixelFormat, PixelsPerScanLine; без FrameBufferBase, PixelInformation masks і framebuffer contents; не викликати SetMode().
5. Memory-map summary: counts сторінок/дескрипторів за типами; без PhysicalStart, VirtualStart, діапазонів чи повної карти.
6. Firmware table presence: тільки acpi_rsdp_present і smbios_present; без адрес, raw bytes, OEM strings, serials, UUID чи asset tags.

Усі значення — pre-boot evidence з явним provenance. Відсутність протоколу/поля лишається unknown або not-exposed, а не «несумісний».

## Заборонені операції та дані

Для автоматичного preflight заборонити:
- будь-який WRMSR, включно з IA32_BIOS_SIGN_ID; довільні MSR writes/reads та PCI configuration-space probing;
- NVRAM, EFI variables, flash, firmware update interfaces;
- ExitBootServices() або власний OS handoff;
- GOP SetMode(), Blt у framebuffer чи зміну display state;
- file writes, розмітку/форматування томів, writable-volume scanning, disk/USB writes;
- raw physical addresses, memory ranges, ACPI/SMBIOS raw tables, SMBIOS serial/UUID/asset tags, framebuffer base, raw CPU registers;
- мережу, package downloads, telemetry або hardware report upload.

Не використовувати probe/physical-boot-probe.c: він записує log на кожен доступний writable volume. Не використовувати probe/exit-boundary-probe.c: він викликає ExitBootServices() і належить до іншого boot-handoff експерименту. Інші entropy/ME/CSME probes не входять у цю задачу.

## Семантичні межі

| Observation | Можна стверджувати | Не можна стверджувати |
| --- | --- | --- |
| GOP mode доступний | Firmware надало pre-boot graphics protocol і mode metadata | Linux DRM/KMS driver bound, connector active або desktop display functional |
| CPUID у QEMU | Ці values повідомила емульована CPU model | Це фізичний CPU |
| ACPI RSDP present | UEFI System Table містить RSDP pointer | Усі ACPI tables валідні/повні |
| SMBIOS entry present | Firmware опублікувала entry point | Усі SMBIOS fields правильні або безпечні |
| UEFI memory map summary | Firmware повідомило snapshot descriptors до завершення Boot Services | Linux MemAvailable, allocator capacity або runtime memory pressure |
| GOP + Linux PCI enumeration | Два окремі evidence sources | Автоматичний зв'язок GOP із конкретним DRM connector без окремого доказу |

### Memory map — лише pre-boot snapshot

UEFI GetMemoryMap() повертає descriptors усіх описаних firmware memory regions, включно з виділеною/зарезервованою пам'яттю. До ExitBootServices() карта належить firmware; allocation буфера може змінити карту, а MapKey змінюється при її зміні. Зберігати тільки агреговані counts з provenance; не прирівнювати до Linux runtime memory.

Джерела: [UEFI 2.11 — GetMemoryMap](https://uefi.org/specs/UEFI/2.11/07_Services_Boot_Services.html), [ACPI 6.6 — UEFI GetMemoryMap](https://uefi.org/specs/ACPI/6.6/15_System_Address_Map_Interfaces.html).

### GOP не є Linux display test

UEFI GOP — програмна абстракція pre-boot graphics. Специфікація надає OS loader mode metadata і framebuffer access до завантаження повноцінного OS graphics driver. GOP presence не доводить Linux DRM/KMS binding або роботу робочого столу.

Джерело: [UEFI 2.11, §12.9 Graphics Output Protocol](https://uefi.org/specs/UEFI/2.11/12_Protocols_Console_Support.html).

### ACPI та SMBIOS privacy

ACPI RSDP призначений для надання фізичної адреси RSDT/XSDT, отже raw pointer/table addresses не потрапляють у report. SMBIOS може містити System Serial Number та UUID; для першого preflight достатньо presence entry point.

Джерела: [ACPI 6.6, §5.2.5 RSDP](https://uefi.org/specs/ACPI/6.6/05_ACPI_Software_Programming_Model.html), [DMTF SMBIOS Specification 3.9.0](https://www.dmtf.org/sites/default/files/standards/documents/DSP0134_3.9.0.pdf).

## Наступний QEMU/OVMF fixture

Після окремого вирішення ліцензійної межі:
- написати незалежний мінімальний EFI application за allowlist вище;
- використати q35/OVMF, 128 MiB, COM1 115200 8N1, display off, reboot disabled, timeout 30s;
- запускати QEMU TCG без host disks, NIC, folder/device passthrough і writable firmware variables;
- передавати тільки обмежений sanitized report через serial;
- маркувати результат qemu-ovmf, не видавати його за physical measurement;
- додати negative tests на address/serial/UUID/raw table/MSR write/SetMode/disk-write leakage та GOP→DRM conflation.

На цьому етапі перевіряти лише serializer і policy. Не підміняти hardware-report.schema.json v1.0.0: окремий pre-boot evidence envelope/versioning потребує погодження з власником schema у #5.

## План та висновок

1. Закріпити source/licensing/security audit.
2. Вирішити ліцензійну межу wsm-os окремо від реалізації.
3. Погодити з #5 окремий versioned pre-boot envelope.
4. Реалізувати незалежний мінімальний UEFI application.
5. Додати sanitized QEMU/OVMF fixture, provenance qemu-ovmf та negative tests.
6. Лише після fixture вирішити, чи інтегрувати provider в installer plan, чи лишити support artifact.

Поточний висновок: повторно використати можна досвід, перелік facts, toolchain discovery та QEMU profile. Наявний probe як є не переносити; clean-room provider ще не реалізовано; фізичний запуск не виконувався.

## Оновлення 2026-11-26: дві нові проби в wsm-os/probe

Перевірка `wsm-os/probe` на 26.11.2026 знайшла дві проби, яких немає в таблиці вище. Обидві свідомо поза межами WSM, і причина не в смаку.

**`physical-boot-probe.c`** пише `\WSM-PROBE-LOG.TXT` на **кожен** writable FAT-том, який бачить firmware. Це прямий конфлікт із політикою read-only preflight ([#3](https://github.com/juv4uk/wsm-desktop/issues/3)): інструмент, який змінює чужі диски, не може бути частиною перевірки, навіть якщо пише лише текстовий лог. Другий ефект — приватність: той самий лог містить адреси й execution state, а файл лягає на носій, який користувач потім комусь передає. Якщо WSM колись знадобить фізичний pre-boot збір, він має писати лише на носій, з якого завантажився, і лише після явної згоди.

**`wsm-probe-driver.c`** — варіант як `EFI_FV_FILETYPE_DRIVER`, вбудований у firmware і автоматично викликаний DXE-диспетчером під час boot, якщо його включено до firmware volume. Це не файловий лог, але й не read-only probe: код читає попередню власну EFI variable через `GetVariable`, збільшує `BootCounter` і викликає `SetVariable` для `WsmProbeData` з `EFI_VARIABLE_NON_VOLATILE | EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS`. Отже, він записує стійкий стан у firmware NVRAM, який переживає перезавантаження; повторний запуск змінює значення лічильника. Окрім цього, driver виконує `WRMSR` для `IA32_BIOS_SIGN_ID` та читає `BOOTGUARD_SACM_INFO`, а також зчитує TSC після `Stall`. Для WSM це поза межами за визначенням: жодних автоматичних firmware-variable writes, MSR writes або boot-time компонентів без явного рішення власника. Окремо слід врахувати upstream-пастку: application і driver не взаємозамінні — driver мусить повернутися, інакше DXE-диспетчер заблокується; саме тому в wsm-os це два окремі файли.

**Ліцензія.** Обидва файли під тією ж ліцензією ВОЛЬНІСТЬ, тому висновок розділу «Ліцензійна межа» вище не змінюється.

**Що з цього варто взяти.** Нічого з коду. Варто взяти дисципліну оформлення: кожна проба в wsm-os має власний заголовок, який пояснює, чому це окремий файл, а не редагування попереднього, і які реальні обмеження середовища він обходить. Для аудиту важливо розрізняти filesystem writes, persistent EFI-variable writes та MSR writes: усі три типи є зміною стану й заборонені автоматичним WSM preflight. Це та сама практика доказовості, якої WSM вимагає від ADR.

Джерела: [physical-boot-probe.c](https://github.com/juv4uk/wsm-os/blob/main/probe/physical-boot-probe.c), [wsm-probe-driver.c](https://github.com/juv4uk/wsm-os/blob/main/probe/wsm-probe-driver.c), [wsm-os/LICENSE](https://github.com/juv4uk/wsm-os/blob/main/LICENSE).
