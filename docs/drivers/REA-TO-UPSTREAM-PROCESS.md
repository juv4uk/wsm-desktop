# Процес REA → незалежна реалізація → upstream → Guix

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: робочий процес для #510–#514 та #519.
- Власник low-level GP107 evidence: [juv4uk/gp107-nvidia-re](https://github.com/juv4uk/gp107-nvidia-re).
- Власник hardware profiles, package policy та інтеграції: цей репозиторій.

## 1. Межі відповідальності

Не створювати паралельні джерела істини.

Що з цих доказів потрібно **десктопу** — і в якому порядку — описано окремо:
[GP107-REVERSE-NEEDS.md](GP107-REVERSE-NEEDS.md). Коротко: реверс не стоїть на
критичному шляху релізу; він потрібен для незалежності від пропрієтарного блоба.

| Рівень | Канонічне місце | Що там зберігати |
| --- | --- | --- |
| Виявлення пристрою й апаратні докази | H170 owner profile та hardware evidence | PCI/USB IDs, ревізії, джерело й рівень спостереження |
| GP107 reverse engineering та фізичні експерименти | [gp107-nvidia-re](https://github.com/juv4uk/gp107-nvidia-re) | REA artifacts, RM ABI observations, probes, raw logs, benchmark harness, capability matrix |
| Рішення WSM | [#510](https://github.com/juv4uk/wsm-desktop/issues/510), [#512](https://github.com/juv4uk/wsm-desktop/issues/512), [#514](https://github.com/juv4uk/wsm-desktop/issues/514), [#519](https://github.com/juv4uk/wsm-desktop/issues/519) | потрібні можливості, обмеження Free/Compatibility, пріоритети, acceptance |
| Відкритий код і патчі | відповідний upstream kernel/Mesa/Guix репозиторій | реалізація, тести, changelog та upstream review |
| WSM-specific інтеграція | цей репозиторій | мінімальні патчі, package manifests, system profile, регресійні тести |

WSM не копіює GP107 raw evidence або harness. Він посилається на конкретний документ, commit, тест і обмеження. Зміна статусу hardware profile потребує доказу відповідного рівня.

## 2. Класи доказів

Кожне твердження має бути одним із таких:

- **confirmed** — підтверджено незалежним відтворюваним тестом або авторитетним джерелом для точної ревізії;
- **observed** — безпосередньо побачено на конкретному хості/пристрої, але межі спостереження обмежені;
- **inferred** — логічний висновок із джерел або кількох спостережень; причина й альтернативи зазначені;
- **unknown** — доказу немає або джерела суперечать одне одному.

Не підміняти одне іншим:

1. пакет існує ≠ пакет розв'язаний у Guix;
2. kernel config має `=m`/`=y` ≠ модуль потрапив у конкретний образ;
3. модуль зібраний ≠ драйвер прив'язався до пристрою;
4. драйвер прив'язався ≠ firmware завантажився;
5. firmware завантажився ≠ функція пройшла тест;
6. один успішний compute workload ≠ повноцінний desktop/display/media stack;
7. benchmark на іншому хості ≠ доказ для H170 reference machine.

У manifest окремо вести `kernel_config`, `package_resolution`, `runtime_binding`, firmware stages та `functional_validation`. Не підвищувати статуси за аналогією.

## 3. REA та незалежна реалізація

REA — засіб отримання перевірюваних знань, а не дозвіл копіювати закритий код.

Допустимий робочий результат дослідження:
- опис спостережуваної поведінки або протоколу;
- точний пристрій, ревізія, версія драйвера/firmware та умови тесту;
- джерело доказу, confidence level, альтернативні пояснення;
- незалежна специфікація поведінки та тестові vectors;
- список прогалин у відкритій реалізації.

Для нової реалізації:
1. спершу перевірити, чи потрібна функція вже є в Linux/Mesa/upstream;
2. відокремити апаратне обмеження від обмеження драйвера, firmware, API чи конфігурації;
3. написати незалежну специфікацію з provenance;
4. відокремити дослідника від реалізатора, якщо доступні окремі агенти/люди: реалізатор отримує лише незалежну специфікацію, provenance та тестові vectors, а не vendor binaries, декомпільований вивід або vendor pseudocode;
5. реалізувати власний код без копіювання vendor source, pseudocode або декомпільованих фрагментів;
6. додати unit/synthetic tests, потім physical tests за дозволом;
7. виміряти регресії та продуктивність;
8. запропонувати загальну зміну upstream; WSM-specific patch залишати лише за документованої причини.

Для GP107 low-level evidence лишається в [канонічній capability matrix](https://github.com/juv4uk/gp107-nvidia-re/blob/master/docs/05-gp107-capability-matrix.md). Дослідницькі приклади й межі описані в [FPC clean-room probe](https://github.com/juv4uk/gp107-nvidia-re/blob/master/docs/03-fpc-clean-room-probe.md), [proprietary artifact ABI facts](https://github.com/juv4uk/gp107-nvidia-re/blob/master/docs/11-proprietary-shipped-artifact-abi-facts.md) та [REA/ICD boundary](https://github.com/juv4uk/gp107-nvidia-re/blob/master/docs/19-rea-icd-boundary-and-memory-controls.md). WSM не створює другу matrix.

## 4. Ліцензійні та технічні межі

WSM Free не залежить від Nonguix, proprietary drivers або nonfree firmware. Відомі nonfree залежності можна описувати в manifest як зовнішні вимоги, але не включати до Free closure.

Особливо уважно ставитися до vendor firmware:
- GP107 GR використовує FECS/GPCCS firmware через ACR; без потрібних blobs fallback повертає `-ENODEV`. Не обходити ACR/signature chain.
- Skylake i915 DMC потрібен для повного DMC-backed runtime power management; базову графіку оцінювати окремо.
- Intel CPU microcode може бути наданий BIOS; OS early-update package є окремою залежністю.
- [NVIDIA Linux driver license](https://www.nvidia.com/en-us/drivers/nvidia-license/), [LICENCE.nvidia](https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware.git/+/133355e89e7f0ab5d61e51eaeda6166c1bb3deb3/LICENCE.nvidia), [Intel LICENSE.i915](https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware/%2B/refs/tags/20250211/LICENSE.i915) та [Intel microcode license](https://github.com/intel/Intel-Linux-Processor-Microcode-Data-Files/blob/main/license) містять обмеження щодо модифікації, зворотного аналізу або перекладу firmware/microcode. Перед декомпіляцією, перекладом firmware, обходом технічного захисту або розповсюдженням похідних матеріалів потрібна окрема правова оцінка застосовного права.

Це не юридичний висновок про всі можливі interoperability exceptions. До правової оцінки працювати з відкритим upstream source, публічною документацією, незалежними hardware observations та власними clean-room реалізаціями. Не зберігати vendor blobs, ключі, дампи або декомпільований код у WSM.

Деталі політики: [ETHICS.md](../ETHICS.md) та [LICENSING.md](../LICENSING.md).

## 5. Фізичні експерименти та безпека

Фізичний тест має бути вузьким, описаним і явно дозволеним.

Для GP107 діє окремий gate [gp107-nvidia-re #18](https://github.com/juv4uk/gp107-nvidia-re/issues/18): read-only preflight не дорівнює Vulkan enumeration. Enumeration/channel init/compute submit можуть створювати тимчасові GPU objects і потребують окремого owner approval. До нього не запускати `vulkaninfo`, enumeration, channel init, submit, reboot або зміни драйвера/firmware.

Не виконувати автоматично:
- BIOS/UEFI, VBIOS, ME/CSME або SSD firmware update;
- destructive storage tests або запис на фізичні диски;
- модифікацію підписаного firmware чи обхід ACR;
- benchmark без фіксації температури, power/clock state, версій і повторів.

VM/QEMU перевіряє збірку та boot, але не доводить фізичний PCI binding, GPU firmware load або performance.

## 6. Бенчмарки та критерій переваги

Порівнювати відкриту й закриту реалізації лише за однакових:
- фізичного GPU та PCI BDF;
- workload, input size, API, buffer memory type та correctness checks;
- kernel, driver, Mesa, ICD, firmware та compiler revisions;
- power/clock/thermal conditions;
- кількості повторів і способу статистичного підсумку.

Окремо вимірювати throughput, latency/frame time, CPU overhead, memory/VRAM, transfer, power та stability. Не називати похідний `effective GB/s` фізичною пропускною здатністю VRAM/PCIe.

Перевага заявляється для конкретного workload і метрики, якщо вона відтворюється та не куплена регресією correctness, stability або security. Універсальна перемога над закритим драйвером не є acceptance criterion.

## 7. Guix та профілі

Pinned Guix channel уже має Mesa 26.2.6 з NVK для x86_64 і Linux-libre 7.3.5 з kernel config для i915, nouveau, alx, HDA, AHCI, NVMe та xHCI. Це усуває потребу створювати fork/override лише для ввімкнення драйверів; це не доводить build, runtime або firmware success.

`systems/wsm-gp107.modconfig` належить лише окремому proprietary NVIDIA Compatibility ISO й навмисно вимикає nouveau/i915. Не використовувати його для Free profile.

Guix інтеграція відбувається після source/license evaluation та package closure review. Free і Compatibility залишаються окремими профілями; nonfree firmware не переходить у Free через спільний package list.

## 8. Готовність задачі

Зміна готова до merge, якщо:
- є чітка проблема, пристрій/ревізія та evidence provenance;
- відділено confirmed/observed/inferred/unknown;
- немає скопійованого vendor code/firmware;
- є тести коректності й regression plan;
- benchmark має baseline та відтворювані умови, якщо заявляється performance win;
- package/profile statuses не підвищені без відповідного proof;
- upstream шлях перевірено, а WSM-specific patch має обґрунтування;
- exact-head CI зелений, diff перевірений, rollback зрозумілий.
