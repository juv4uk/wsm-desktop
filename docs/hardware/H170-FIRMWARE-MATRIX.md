# H170: матриця драйверів, firmware та microcode

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Дата аудиту: 2026-11-28.
- Ціль: Gigabyte GA-H170-Gaming 3, Intel Core i5-6400, Intel HD Graphics 530, NVIDIA GTX 1050 Ti (GP107), Killer Ethernet, HDA audio, SATA, NVMe, USB.
- Джерело апаратної ідентичності: [OWNER-HARDWARE-REFERENCE.md](OWNER-HARDWARE-REFERENCE.md) та [wsm-os OWNER-HARDWARE-PROFILE](https://github.com/juv4uk/wsm-os/blob/main/docs/OWNER-HARDWARE-PROFILE.md).
- Статус: статичний source/license audit; не є фізичною Linux functional certification.

## 1. Ключовий висновок

Базові відкриті host drivers уже присутні в типовій конфігурації
Linux-libre 7.3.5 із pinned Guix channel. Mesa 26.2.6 у цьому каналі
вже збирається з NVK для x86_64. Отже, власні kernel patches або Mesa
fork лише для ввімкнення i915/Nouveau/NVK/alx/HDA/AHCI/NVMe не потрібні.

Головна перешкода повної свободи — не package recipe, а firmware:
- GP107 GR 3D/compute потребує NVIDIA-signed FECS/GPCCS firmware через ACR;
- Skylake i915 DMC потрібен для повного display runtime power management;
- Intel CPU OS microcode update є окремим невільним пакетом, хоча BIOS уже надає старішу ревізію.

Наявність драйвера в kernel config не доводить package closure, runtime binding, firmware load або функціональність. Усі ці стани ведуться окремо.

## 2. Матриця пристроїв

| Пристрій | Відкритий host driver / шлях | Host firmware | Відомий вплив / обмеження | Доказ і статус |
| --- | --- | --- | --- | --- |
| Intel Core i5-6400 (Skylake) | x86 CPU + kernel microcode loader | OS update optional, nonfree; BIOS уже містить 0xC2 | Без раннього Intel package Linux використовує BIOS 0xC2; Windows owner evidence показує 0xD6 | CPUID 0x506E3, BIOS/UEFI 0xC2, Windows 0xD6 у [wsm-os FIT analysis](https://github.com/juv4uk/wsm-os/blob/main/hardware/bios-f22e/FIT-AND-STRUCTURE-ANALYSIS.md). Runtime Linux revision не перевірена |
| Intel HD Graphics 530 | i915, Mesa | DMC optional/nonfree; GuC/HuC окремі optional capabilities | Без DMC i915 вимикає runtime power management; це не означає відсутність базової графіки | [i915 DMC source](https://kernel.googlesource.com/pub/scm/linux/kernel/git/soc/soc/+/e805c06a80fb657f568ea36600a8e1e6746c2987/drivers/gpu/drm/i915/display/intel_dmc.c); exact physical binding не перевірений |
| NVIDIA GTX 1050 Ti / GP107 | nouveau + Mesa NVK | GR FECS/GPCCS required/nonfree | Без потрібної firmware fallback повертає -ENODEV для GR. На окремому GP107 witness host зафіксовано Nouveau binding і один vector-add compute run під Kali 7.2.15/Mesa 26.1.6; однак [docs/18](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/18-procedural-deviation-and-benchmark-reliability.md) підтверджує, що погоджений source/BTF preflight не був повністю завершений до dispatch (**procedural deviation**). Зберігати це лише як історичний device-level runtime witness, не як clean acceptance, поточний benchmark baseline чи H170 доказ. Motherboard/CPU/BIOS witness host не доводять H170 тотожність; package/blob GR firmware не ідентифіковано. [GP107 docs/39](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/39-gp107-nouveau-firmware-dependency-map.md) — source-only map GR FECS/GPCCS, ACR, SEC2 і NVDEC шляхів, не boot request/load чи Guix closure evidence. Basic KMS/display та power/reclocking оцінюються окремо | [Pinned GP107 firmware map](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/39-gp107-nouveau-firmware-dependency-map.md), [historical NVK compute witness](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/14-nvk-vector-add-compute-result.md), [procedural deviation](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/18-procedural-deviation-and-benchmark-reliability.md), [Nouveau feature matrix](https://nouveau.freedesktop.org/FeatureMatrix.html). Historical external runtime witness only; not current acceptance/benchmark baseline; H170 runtime_binding remains unknown and WSM Free profile remains not-run |
| Killer Ethernet (Windows label E2200) | alx candidate | Не потрібна зовнішня host firmware | alx source не містить request_firmware/MODULE_FIRMWARE у перевірених файлах. Точний PCI ID невідомий | Owner profile: Windows label E2200. GIGABYTE Rev. 1.0 вказує E2201, Rev. 1.1 — E2400; [Rev. 1.0 spec](https://www.gigabyte.com/Motherboard/GA-H170-Gaming-3-rev-10/sp), [Rev. 1.1 spec](https://www.gigabyte.com/Motherboard/GA-H170-Gaming-3-rev-11/sp). Не виводити PCI ID з назви |
| HDA audio | snd_hda_intel + Realtek codec candidate | Не потрібна для стандартного codec path | Optional user-supplied HDA patch loader — окрема override; не vendor firmware. Board spec lists ALC1150, exact codec ID не спостерігався | [HDA notes](https://cdn.kernel.org/doc/html/latest/sound/hd-audio/notes.html), [GIGABYTE Rev. 1.0](https://www.gigabyte.com/Motherboard/GA-H170-Gaming-3-rev-10/sp) |
| SATA/AHCI + Samsung drives | ahci | Не потрібна зовнішня host firmware для generic AHCI | Внутрішня firmware диска — окремий компонент пристрою, не host package Guix | [Linux AHCI source](https://github.com/torvalds/linux/blob/master/drivers/ata/ahci.c); disk firmware не перевірялася й не оновлювалася |
| Kingston NV2 / NVMe | nvme host driver | Не потрібна зовнішня host firmware для generic NVMe | Внутрішня firmware SSD окрема; не плутати з host driver dependency | [Linux NVMe host source](https://github.com/torvalds/linux/tree/master/drivers/nvme/host); SSD firmware не перевірялася й не оновлювалася |
| USB / xHCI | xhci-pci + xhci-hcd | Intel PCI xHCI path не запитує зовнішню firmware; окремий Renesas controller driver має firmware loader, але це не Intel H170 PCH | Типовий kernel config має xHCI built-in; конкретні USB периферійні пристрої не інвентаризовані | [xhci-pci source](https://github.com/torvalds/linux/blob/master/drivers/usb/host/xhci-pci.c), [Renesas-specific firmware loader](https://github.com/torvalds/linux/blob/master/drivers/usb/host/xhci-pci-renesas.c) та pinned Linux-libre config; physical USB enumeration не виконувалася |
| Intel MEI/HECI PCI function | mei_me | Не потрібна host firmware | HECI PCI ID 8086:a13a та базовий MKHI обмін фізично перевірені через `/dev/mei0` у Kali Linux; WSM Guix binding ще не перевірений | [wsm-os HECI trace](https://github.com/juv4uk/wsm-os/blob/main/docs/HECI-HARDWARE-TRACE.md), pinned Linux-libre config (`CONFIG_INTEL_MEI=m`, `CONFIG_INTEL_MEI_ME=m`) |
| Intel ME/CSME firmware | Pre-OS firmware in motherboard BIOS/SPI | ME 11.8.50.3425 — nonfree platform firmware | Не є Linux driver firmware package; працює до ОС і лишається в BIOS/SPI domain | [CSME architecture](https://github.com/juv4uk/wsm-os/blob/main/hardware/CSME-ARCHITECTURE.md). Не дублювати ME region/raw dumps |

## 3. Guix/Linux-libre package facts

Pinned Guix channel commit
`4e5195be20d9b124df8a8bb69213412236e4668e` (2026-11-25):
- Mesa 26.2.6 для x86_64 має `-Dvulkan-drivers=amd,intel,intel_hasvk,nouveau,swrast,virtio` та Cargo inputs для NVK.
- Default `linux-libre` alias — 7.3.5.
- Default `7.3-x86_64.conf` має i915, nouveau, alx, HDA/Realtek, AHCI, NVMe, xHCI та CPU microcode loader.

Джерела: [Mesa package](https://codeberg.org/guix/guix/src/commit/4e5195be20d9b124df8a8bb69213412236e4668e/gnu/packages/gl.scm), [Linux packages](https://codeberg.org/guix/guix/src/commit/4e5195be20d9b124df8a8bb69213412236e4668e/gnu/packages/linux.scm), [kernel config](https://codeberg.org/guix/guix/src/commit/4e5195be20d9b124df8a8bb69213412236e4668e/gnu/packages/aux-files/linux-libre/7.3-x86_64.conf), [NVK requirements](https://docs.mesa3d.org/drivers/nvk.html).

Це package-source/config evidence, не доказ, що конкретний WSM ISO вже зібрано або що модулі завантажилися на фізичній H170.

### 3.1. NVK у точному upstream Mesa 26.2.6: source-only аудит GP107

Тарґет для цього висновку — upstream tag `mesa-26.2.6`, commit
`8e87a503ebd91408c88596d1b9eeb5f4c0b2088d` (tag object
`66b63490b62bc685f7075cb9f99d26747ff8d80f`). Release archive має SHA-256
`b9436b3e1a8be76fbd4823dc884f90596ab7c6ac5e1867a305e66ffccfb31a92`.
Guix channel лишається pinned на `4e5195be20d9b124df8a8bb69213412236e4668e`;
цей аудит не змінює lock, Guix recipe чи package inputs.

За точним source snapshot:

- `nvk_get_vk_version()` повертає Vulkan 1.2 до Maxwell, 1.3 для класів
  від Maxwell до Turing, і 1.4 від Turing. Pascal/GP107 тому має source policy
  Vulkan 1.3 (якщо немає зовнішнього version override).
- `nvk_is_conformant()` відхиляє non-discrete devices, але позначає discrete
  класи Kepler–Ada conformant. Для дискретної GTX 1050 Ti / GP107 це означає,
  що Pascal не потрапляє в non-conformant escape hatch лише через свій клас.
- `nvk_create_drm_physical_device()` відхиляє покоління до Kepler і створює
  NVK physical device тільки після успішного `nvkmd_try_create_pdev_for_drm()`;
  окремий compiler object створюється через `nak_compiler_create()`.
- Nouveau KMD path вимагає DRM render node, PCI vendor NVIDIA, успішне
  розпізнавання Nouveau на render fd та `has_vm_bind`. Саме джерело
  `drm_device_is_nouveau()` відкриває render node з `O_RDWR|O_CLOEXEC`;
  отже, цей кодовий шлях не слід називати суто read-only physical probe.
  У вихідному коді коментар прямо фіксує Linux kernel 6.6+ як вимогу NVK.
- Дискретний NVK physical device має graphics/compute/transfer queue family;
  це оголошення можливостей у source, а не доказ успішного GR channel init
  чи compute dispatch на цій машині.

**Висновок:** `GP107_SOURCE_ELIGIBLE=YES` для NVK у Mesa 26.2.6 за device-class
policy та compile-time source path. Це не дорівнює
`H170_RUNTIME_BINDING=PASS`, `GR_FIRMWARE_AVAILABLE=YES`,
`NVK_ENUMERATION=PASS` або `COMPUTE=PASS`.

#### Незакриті залежності

- NVIDIA-signed FECS/GPCCS firmware для GP107 GR — окремий nonfree dependency.
  Source-level eligibility NVK не створює firmware, не обходить ACR/signature
  chain і не дозволяє включати ці blobs у WSM Free closure.
- Цей аудит не доводить, що firmware package присутній у pinned Guix closure,
  initrd, live image або встановленій системі; для цього потрібен окремий
  package/closure/manifest audit без читання чи декомпіляції blob.
- Не доведено, що конкретний H170 завантажить Nouveau, отримає render node,
  `VM_BIND`, потрібну firmware або підніме GR.
- Зовнішній GP107 vector-add witness на Kali/Mesa 26.1.6 залишається окремим
  device-level свідченням. Він не переноситься на Mesa 26.2.6, H170 чи strict
  WSM Free profile.
- Intel HD 530 DMC лишається окремою optional/nonfree capability для повного
  runtime power management; її відсутність не скасовує базовий i915 display path.

Джерела для точного snapshot:
[Mesa 26.2.6 release notes and archive hash](https://docs.mesa3d.org/relnotes/26.2.6.html),
[upstream Mesa 26.2.6 tag/commit](https://chromium.googlesource.com/chromiumos/third_party/mesa/+/refs/tags/upstream/mesa-26.2.6),
[NVK physical-device policy](https://chromium.googlesource.com/chromiumos/third_party/mesa/+/refs/tags/upstream/mesa-26.2.6/src/nouveau/vulkan/nvk_physical_device.c),
[Nouveau DRM/VM_BIND gates](https://chromium.googlesource.com/chromiumos/third_party/mesa/+/refs/tags/upstream/mesa-26.2.6/src/nouveau/vulkan/nvkmd/nouveau/nvkmd_nouveau_pdev.c).

### 3.2. GP107 Nouveau firmware dependency map

Зовнішній GP107 source audit [docs/39](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/39-gp107-nouveau-firmware-dependency-map.md)
закріплює Linux source `f4585067150b85e33f60876149a6e742928da75e` та
linux-firmware WHENCE snapshot. Він показує GP107 GR FECS/GPCCS і software
context paths, спільні GP102 ACR paths, дві SEC2 version candidates та NVDEC
scrubber path. Це лише source/manifest evidence: не встановлено, які з
кандидатів запитав або завантажив конкретний boot, і не доведено їх наявність
у Guix package closure, initrd, live ISO чи installed rootfs. Pairing цього
Linux source із фактичним `nouveau.ko` окремого witness host також не
підтверджено.

`WHENCE` відсилає до `LICENCE.nvidia`. Її §2.1.2 дозволяє копіювання та
розповсюдження firmware binaries лише для використання на операційних системах,
які розповсюджуються під OSI-approved open-source license; binaries мають бути
незміненими, а копія ліцензії — супроводжувати їх. WSM `LicenseRef-Volnist`
прямо не є OSI-визнаною (`docs/LICENSING.md`), а issue #367 щодо власної
ліцензійної класифікації лишається відкритим. Тому статус Compatibility
`opt-in` не можна вважати достатнім доказом виконання §2.1.2.

Консервативна WSM release policy: **не включати та не перерозповсюджувати
NVIDIA firmware через WSM Free або Compatibility channel/ISO**, не додавати
автоматичний downloader і не публікувати firmware assets, доки власник/юрист
письмово не підтвердить правову підставу для конкретної моделі розповсюдження.
Це package/release gate, а не остаточний юридичний висновок про будь-яке
особисте використання firmware поза WSM distribution. Жодних firmware blobs
або похідних payloads до репозиторію не додавати.


## 4. Відомі невільні залежності та ліцензійні межі

- GP107 firmware group у linux-firmware поширюється за `LICENCE.nvidia`; це не open firmware. NVIDIA license містить заборони на firmware translation, reverse engineering/decompilation/disassembly binary software та обхід authentication mechanisms.
- Intel i915 firmware та CPU microcode поширюються за окремими Intel licenses; binary redistribution не означає право модифікувати або декомпілювати.
- Free profile може документувати відому nonfree залежність, але не включати її. Compatibility profile — окремий opt-in і не змінює Free closure.
- Перед прямим REA firmware/microcode binary потрібна окрема правова оцінка застосовного права. Не обходити ACR/signature chain, не зберігати vendor blobs і не створювати похідні firmware без підтверджених прав.

Джерела: [linux-firmware WHENCE](https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware/+/refs/heads/main/WHENCE), [NVIDIA Linux license](https://www.nvidia.com/en-us/drivers/nvidia-license/), [LICENCE.nvidia](https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware.git/+/133355e89e7f0ab5d61e51eaeda6166c1bb3deb3/LICENCE.nvidia), [Intel LICENSE.i915](https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware/%2B/refs/tags/20250211/LICENSE.i915), [Intel microcode license](https://github.com/intel/Intel-Linux-Processor-Microcode-Data-Files/blob/main/license).

## 5. Межі продуктивності

- NVK офіційно охоплює Kepler і новіші покоління, включно з Pascal, та потребує Linux 6.6+; pinned Guix stack відповідає цій вимозі.
- **Зовнішній device-level факт:** на окремому GP107 research host з GTX 1050 Ti пройшов один clean-room NVK vector-add workload (1024 елементи, fence, host readback, checksum match). Це доводить, що Nouveau/NVK може виконувати compute на GP107 у Kali Linux 7.2.15/Mesa 26.1.6; motherboard/CPU/BIOS цього test host не доведені як H170 reference machine.
- Firmware provenance того запуску не записаний. GR firmware, необхідна для успішного compute, була доступна в тестовому середовищі, але package/blob/version не зафіксовано; `pmu: firmware unavailable` у kernel log стосується окремого PMU шляху. Тому цей результат не доводить, що strict WSM Free closure може повторити тест.
- У gp107-nvidia-re є proprietary-only baseline та optimization matrix; попередній NVK-vs-NVIDIA A/B (docs/17) є історичним і передує виправленням надійності harness (docs/18). Сучасний NVK A/B на виправленому harness ще не виконано.
- Proprietary-only docs/21 містить 108 HOST_VISIBLE/HOST_COHERENT host-side submit-to-completion points; це корисна exploratory matrix, але не VRAM bandwidth і не GPU-only duration. docs/22 (DEVICE_LOCAL transfer/compute) наразі позначено EXPLORATORY / NOT ACCEPTED через відсутні Vulkan memory dependencies між H2D → compute → D2H, неперевірений `memoryTypeBits` та відсутність окремих GPU timestamp measurements. Не використовувати її 90.46 GB/s чи 52.39 ms як валідні performance conclusions до виправлення та повторного запуску. VRAM residency, batching і зменшення копій залишаються гіпотезами для коректного NVK A/B, а не доведеними оптимізаціями.
- Для прийнятного A/B обов'язкові: Vulkan memory barriers H2D→compute→D2H→host-read, перевірка `memoryTypeBits` кожного allocation, synchronization validation (якщо доступна), правильний readback/checksum, окремі host submit-to-completion latency та GPU timestamp queries з `timestampValidBits`/`timestampPeriod`, а також temperature/power/clock capture.
- Не заявляти перевагу над NVIDIA, доки не буде коректного A/B на тому самому GP107, workload, memory type, clocks/thermal state та версіях.

Канонічні GPU дослідження: [gp107-nvidia-re](https://github.com/juv4uk/gp107-nvidia-re), [benchmark reliability issue](https://github.com/juv4uk/gp107-nvidia-re/issues/28).

## 6. Зовнішній physical NVK witness та межа профілю

[GP107 docs/13](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/13-nouveau-nvk-boot-witness-result.md) підтверджує на зовнішньому GP107 test host `Kernel driver in use: nouveau`, NVK `driverID=24`, Mesa 26.1.6 та Vulkan API 1.3.354; це не доказ, що host є H170 reference machine. [docs/14](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/14-nvk-vector-add-compute-result.md) підтверджує один реальний GPU dispatch, fence, host readback і checksum. Це **functional smoke**, не benchmark.

Тест виконано на окремому GP107 test host з Kali Linux 7.2.15, а не на доведеній H170 reference machine і не на pinned Guix Mesa 26.2.6/Linux-libre 7.3.5. Точний пакет і hash GR firmware у capture не зафіксовано; успішний GR compute означає, що необхідна firmware була доступна, але не доводить її походження або ліцензійний склад. У kernel log є `pmu: firmware unavailable`; це окремий PMU firmware path і він не завадив цьому workload. Через це `h170-free.json` зберігає `runtime_binding=unknown` та `functional_validation=not-run` для H170/strict Free profile; candidate evidence лише посилається на зовнішній GP107 test host.

Попередній NVK/NVIDIA A/B з docs/17 позначено історичним після виправлень надійності в docs/18. Актуальний benchmark на виправленому harness ще не виконаний.

## 7. Що ще невідомо / потребує owner-approved перевірки

- Точна ревізія GA-H170-Gaming 3 та точний PCI ID Killer Ethernet.
- Фактичний codec ID HDA; ALC1150 підтверджений лише специфікацією плати.
- Фізичний Linux driver binding на самій H170 для всіх пристроїв, firmware load stages, suspend/resume, audio/network/storage I/O. Зовнішній GP107 host не замінює H170 inventory.
- H170-specific NVK enumeration/channel/runlist correlation та GP107 runtime A/B. Зовнішній GP107 compute witness уже існує, але був виконаний до завершення повного preflight (це задокументовано в GP107 docs/18). За gp107-nvidia-re #18 повторні Vulkan enumeration/channel init/submit/reboot потребують завершення preflight та окремого explicit owner approval.
- Повна Guix system build/ISO closure та physical boot на H170.

До виконання цих перевірок manifest зберігає `not-assessed`, `unknown` та `not-run`; не перетворює package/config evidence на hardware certification.


## 8. Реалістичність незалежної відкритої реалізації

| Компонент | Поточна оцінка | Що реально робити | Межа / що не обіцяти |
| --- | --- | --- | --- |
| GP107 GR FECS/GPCCS | **Hard limit для поточного Free path** | Продовжувати відкритий Nouveau/NVK driver work, досліджувати публічні протоколи та незалежні hardware observations у межах прав | Без потрібної NVIDIA-signed firmware upstream fallback повертає `-ENODEV`; звичайний kernel patch не замінить signed Falcon firmware. Відкриту сумісну firmware реалізацію не знайдено |
| GP107 Pascal reclocking | **Hard limit у поточному Nouveau** | Оптимізувати queueing, memory residency, synchronization та userspace workloads у доступному power state | Nouveau Feature Matrix вказує на відсутність практичного reclocking шляху для GP10x через підписані firmware. Не обіцяти частоти/продуктивність на рівні NVIDIA proprietary |
| Intel HD 530 DMC | **Обмежена функціональність** | Зберегти відкритий i915/Mesa; оптимізувати базову графіку та workload paths; окремо вимірювати idle/power | Без nonfree DMC firmware upstream вимикає runtime power management. Відкриту заміну DMC не підтверджено |
| Intel GuC/HuC | **Optional capability gap** | Перевірити workloads, які реально потребують GuC/HuC; оптимізувати доступні без них шляхи | Не називати media/scheduling capabilities доступними без відповідного firmware evidence |
| Intel CPU microcode | **Nonfree optional update** | Використовувати BIOS-provided 0xC2 у Free profile; фіксувати revision у benchmark metadata | OS update до 0xD6 потребує Intel nonfree package. Відкритої заміни microcode не знайдено; не декомпілювати blob |
| Intel ME/CSME | **Pre-OS domain, поза Guix host closure** | Підтримувати відкритий host-side MEI/HECI driver та документувати доступні інтерфейси | ME 11.8.50.3425 лишається в BIOS/SPI. Це не Linux driver firmware; не обіцяти заміну CSME в межах desktop profile |
| Killer E2200 family / alx | **Software-optimization opportunity** | Оптимізувати open alx path лише за виміряного bottleneck; перевірити точний PCI ID | Зовнішня host firmware не потрібна у перевіреному alx source; точний silicon/PCI ID ще unknown |
| HDA / Realtek | **Software-optimization opportunity** | Налаштувати ALSA/UCM, codec verbs та power states після точного codec enumeration | Базовий HDA path не потребує vendor firmware; ALC1150 поки board-spec evidence, не фізично прочитаний codec ID |
| SATA/AHCI, NVMe, USB/xHCI | **Software-optimization opportunity** | Профілювати I/O queues, scheduler, latency та power; окремо тестувати кожний пристрій | Host driver не потребує зовнішнього firmware у перевірених шляхах; firmware всередині SSD/контролера не є Guix host package |

**Важливо:** "Hard limit" означає, що в цьому аудиті не знайдено підтвердженого відкритого й законного шляху до повної функції. Це не твердження про математичну неможливість майбутнього рішення. Не обходити ACR/signature chain і не робити firmware reverse engineering без окремої правової оцінки.

## 9. Завершення статичного аудиту та наступні перевірки

Статичний firmware/license audit вважається завершеним, коли:
- кожен відомий H170 компонент має host-driver/firmware classification або явний unknown;
- відомі nonfree firmware/microcode не приховані як unknown і не включені до Free closure;
- кожен висновок має джерело та межу доказу;
- physical/runtime checks винесені в окремі задачі.

Залишкові physical/runtime роботи ведуться окремо:
- #511 — benchmark baseline та актуальний NVK A/B;
- #512 — GP107 capability gaps та H170 decision;
- #514 — Guix profile build/closure та фізична інтеграція.

До окремого owner approval не виконувати GPU enumeration, Vulkan channel init/submit, reboot, firmware update або destructive storage tests.


## 10. Мінімальна acceptance matrix саме для H170

Це план майбутньої перевірки, не твердження, що тести вже виконані.
Кожен результат має бути прив'язаний до exact H170 board revision,
BIOS F22e, CPU CPUID, PCI ID/BDF, kernel, Mesa, driver та firmware
package/hash. Зовнішній GP107 test host не замінює H170.

| Рівень | Підсистема | Мінімальний тест | Умови / межі |
| --- | --- | --- | --- |
| 0 — build | Guix / Linux-libre | Чиста оцінка й збірка system closure, kernel, Mesa, ICD та initrd; перевірка, що nonfree firmware не потрапила у Free closure | Без фізичного boot; зафіксувати channel commit і closure |
| 1 — read-only inventory | CPU / PCI / USB | CPUID + microcode revision; `lspci -nnk`; `lsusb -t`; module/config/firmware metadata | Без module reload, PCI config writes, reboot або firmware update |
| 1 — read-only inventory | MEI/HECI | Перевірити `/dev/mei*`, module binding та read-only version query | Базовий MKHI вже фізично пройшов у Kali; повтор на WSM Guix окремо |
| 2 — functional | Ethernet | Link negotiation, packet loss, throughput і reconnect | Не змінювати permanent network config; фіксувати точний PCI ID |
| 2 — functional | HDA | Playback + capture, codec enumeration, jack/mixer controls | Підтвердити фактичний codec ID, не лише board spec |
| 2 — functional | SATA/NVMe | SMART/read-only health + file-backed read/write/checksum test | Тільки тимчасові файли на явно обраному томі; жодних destructive/raw-device tests |
| 2 — functional | USB | Контролер/порт topology, input devices та file-backed transfer test | Не прошивати периферію; зафіксувати speed/port/controller |
| 2 — functional | Intel HD 530 | KMS/modeset, OpenGL render, video decode/encode capability checks | DMC absent означає окремо позначений runtime-PM gap; не плутати з базовою графікою |
| 2 — functional | GTX 1050 Ti / Nouveau | KMS/display, OpenGL, Vulkan device enumeration, NVK compute witness і correctness/readback | Vulkan enumeration/channel init/submit — лише після GP107 #18 preflight та explicit owner approval; external GP107 witness не є H170 proof |
| 3 — performance | CPU/GPU/memory | Repeatable workload matrix: sizes, workgroup sizes, batching, HOST_VISIBLE vs DEVICE_LOCAL, transfer/compute/readback phases | Однакові firmware, clocks, thermals, driver versions, correctness checks; memory barriers + memoryTypeBits checks; synchronization validation; окремі host latency та GPU timestamps; best-effort Nouveau hwmon temperature; median + spread, не один запуск |
| 3 — power/stability | GPU/CPU/system | Idle/load power, clock/temperature, long-run stability, suspend/resume | Окреме explicit approval; не виконувати автоматично під час benchmark bring-up |

### Критерій прийняття

- **Build pass**: точний Guix closure зібрався; не означає hardware support.
- **Driver-bound pass**: конкретний модуль прив'язався до exact PCI ID/BDF на H170.
- **Firmware pass**: усі потрібні файли й версії встановлено/завантажено; для Free closure — тільки дозволені компоненти.
- **Functional pass**: workload пройшов correctness/readback та повторюється.
- **Performance win**: порівняння з baseline на тій самій H170 і в однакових умовах; не переносити результати з GP107 test host.
- **Profile pass**: усі попередні рівні підтверджені саме для заявленого профілю (Free або Compatibility), а manifest зберігає provenance.

Поки ці критерії не виконані, H170 profile залишається draft, а невідомі стани не підвищуються.

## 11. Поза-GPU firmware-блоби: статичний інвентар (GP107 відкладено)

Зріз: `main@b7c6be06239dc4567cfb954e9c6882278458170a`. Цей розділ фіксує лише невідео залежності вашої H170-машини. GP107/GPU блоби свідомо не розглядаються тут і переносяться в окремий етап. Статус рядків нижче — source/license evidence; він не доводить наявність файлу в Guix closure, initrd/rootfs, runtime load або фізичну функцію на цій платі.

| Компонент | Блоб / шлях | Статус для H170 Free | Що доведено з джерел | Що лишається `not-assessed` / `unknown` |
| --- | --- | --- | --- | --- |
| Intel Core i5-6400, CPUID `0x506E3` | `kernel/x86/microcode/GenuineIntel.bin` — optional OS early update | `optional`, `nonfree`, не входить у Free closure | BIOS F22e вже містить мікрокод `0xC2` (2017-11-16); Windows пізніше повідомляв `0xD6` (2019-10-03). Linux може стартувати на BIOS-версії `0xC2`; пінений kernel config має `CONFIG_MICROCODE=y` і вимикає late-load. Ліцензія Intel допускає бінарне поширення без модифікації й забороняє RE/disassembly | наявність package у точному Guix closure/initrd, фактичну Linux-версію після boot, застосовність оновлення до цього CPU |
| Intel HD Graphics 530 (Skylake i915) | Skylake DMC (та окремо GuC/HuC) | `optional`, `nonfree` (`LICENSE.i915`), не входить у Free closure | DMC потрібен для DMC-backed runtime power management; без нього upstream вимикає runtime PM, але базова графіка є окремим шляхом. GuC/HuC — окремі workload-specific capabilities | package presence, module binding, `/dev/dri`, фактичний runtime-PM стан і display/KMS на цій H170 |
| Intel ME/CSME | Pre-OS firmware у BIOS/SPI, ME `11.8.50.3425` | не host-loadable, поза Guix host closure | Це не Linux driver firmware; працює до ОС. Не дублювати ME region/raw dumps | жодних нових дампів, RE чи оновлень ME у цій роботі не виконувалося |
| Killer Ethernet (Windows label E2200) | немає host firmware blob у перевіреному alx шляху | `not-required`, точний PCI ID `unknown` | У перевіреному open-source шляху alx немає `request_firmware`/`MODULE_FIRMWARE`; початковий Windows-підпис пристрою не дає PCI ID | точний PCI ID/revision і Linux binding на цій платі |
| HDA / Realtek | стандартний codec-шлях не потребує vendor blob; `snd-hda-patch-loader` — лише optional user-supplied patch | `not-required`, exact codec ID `unknown` | Kernel HD-audio docs описують базовий шлях без vendor firmware; patch loader є окремою опцією, не baseline dependency | фактичний codec ID (ALC1150 — лише board-spec), UCM, playback/capture |
| SATA/AHCI та Samsung/NVMe | generic `ahci` / `nvme` host drivers не запитують host firmware | `not-required`, device-internal firmware окремо | Внутрішня прошивка дисків є device-managed і не є host-loadable Guix dependency | версії firmware дисків, SMART/health і будь-які write tests |
| USB / xHCI | Intel PCH xHCI — зовнішня firmware не потрібна; Renesas loader не стосується цієї плати | `not-required` для Intel шляху | Pinned kernel config і xHCI source не показують зовнішній firmware запит для Intel контролера | перелік периферійних пристроїв, port topology і функційні transfer tests |

### Відповідність до рекомендацій #171

У #171 зафіксовано «Черговість реверсу» (коментар `2026-11-27T23:26:09Z`):

- **P0** — ідентифікація конкретних H170 компонентів і нативний Linux binding;
- **P1** — GP107 Nouveau firmware dependency map (exact kernel-requested names, WHENCE `File/RawFile/Link`, symlink targets, license, initrd/rootfs);
- **P2** — FIFO channel/runlist/non-stall correlation;
- глибше декодування R580 UVM/RM — відкласти.

Оскільки GPU відкладено, P1 і P2 тут не виконуються. Для невідео-пристроїв coordinator-рішення в тому самому issue (`2026-11-28T02:35:52Z`) прямо каже: «No WSM-owned reverse engineering or generic driver pack indicated» — тобто потрібен read-only native H170 inventory, а не реверс бінарників. Цей розділ фіксує лише source/license інвентар; **P0 залишається NOT_RUN** і потребує окремого owner-approved запуску на реальній машині, а не емуляції в WSL/QEMU.

Спільні межі цього інвентарю:

- жодні бінарні blobs, firmware образи, ключі або дампи до репозиторію не додаються;
- статуси `live_rootfs`, `initrd`, `installed_rootfs`, `runtime_load` і `functional_validation` у `drivers/profiles/h170-free.json` лишаються `not-assessed`/`not-run`, доки не буде окремого native H170 `wsm-hwcheck` report;
- Nonfree Intel firmware/pkg не входить у Free closure; Compatibility/ліцензійні рішення ведуться окремо за #171 і чинним release gate;
- тут не виконувалися GPU enumeration, CUDA/NVML, RM/UVM/D3DKMT ioctl, MMIO, firmware update, reboot, tag або release; GP107 залишається відкладеним.

Джерела вже наведені вище в §2–§4 і в [h170-free.json](../../drivers/profiles/h170-free.json); цей розділ лише збирає їх у поза-GPU інвентар, а не додає нову hardware чи runtime сертифікацію.
