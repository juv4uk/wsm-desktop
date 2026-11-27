# H170: матриця драйверів, firmware та microcode

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Дата аудиту: 2026-11-27.
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
| NVIDIA GTX 1050 Ti / GP107 | nouveau + Mesa NVK | GR FECS/GPCCS required/nonfree | Без потрібної firmware fallback повертає -ENODEV для GR; 3D/compute не можна заявляти. Basic KMS/display — окреме неперевірене питання. Pascal GP10x не має практичного reclocking шляху | [GP107 firmware declarations](https://linux.googlesource.com/linux/kernel/git/tip/tip/+/refs/heads/perf/urgent/drivers/gpu/drm/nouveau/nvkm/engine/gr/gp107.c), [no-firmware fallback](https://linux.googlesource.com/linux/kernel/git/tip/tip/+/refs/heads/x86/urgent/drivers/gpu/drm/nouveau/nvkm/engine/gr/gm200.c), [Nouveau feature matrix](https://nouveau.freedesktop.org/FeatureMatrix.html). H170 physical runtime не перевірений |
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

## 4. Відомі невільні залежності та ліцензійні межі

- GP107 firmware group у linux-firmware поширюється за `LICENCE.nvidia`; це не open firmware. NVIDIA license містить заборони на firmware translation, reverse engineering/decompilation/disassembly binary software та обхід authentication mechanisms.
- Intel i915 firmware та CPU microcode поширюються за окремими Intel licenses; binary redistribution не означає право модифікувати або декомпілювати.
- Free profile може документувати відому nonfree залежність, але не включати її. Compatibility profile — окремий opt-in і не змінює Free closure.
- Перед прямим REA firmware/microcode binary потрібна окрема правова оцінка застосовного права. Не обходити ACR/signature chain, не зберігати vendor blobs і не створювати похідні firmware без підтверджених прав.

Джерела: [linux-firmware WHENCE](https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware/+/refs/heads/main/WHENCE), [NVIDIA Linux license](https://www.nvidia.com/en-us/drivers/nvidia-license/), [LICENCE.nvidia](https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware.git/+/133355e89e7f0ab5d61e51eaeda6166c1bb3deb3/LICENCE.nvidia), [Intel LICENSE.i915](https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware/%2B/refs/tags/20250211/LICENSE.i915), [Intel microcode license](https://github.com/intel/Intel-Linux-Processor-Microcode-Data-Files/blob/main/license).

## 5. Межі продуктивності

- NVK офіційно охоплює Kepler і новіші покоління, включно з Pascal, та потребує Linux 6.6+; pinned Guix stack відповідає цій вимозі.
- Але GP107 GR firmware та Pascal reclocking — окремі обмеження. Відкритий kernel driver + Mesa package не гарантують повної продуктивності.
- У gp107-nvidia-re є сучасна proprietary-only baseline та optimization matrix; попередній NVK-vs-NVIDIA A/B оголошений історичним після виправлення harness. Сучасний NVK A/B на тому самому harness ще не виконано.
- Не заявляти перевагу над NVIDIA, доки не буде коректного A/B на тому самому GP107, workload, memory type, clocks/thermal state та версіях.

Канонічні GPU дослідження: [gp107-nvidia-re](https://github.com/juv4uk/gp107-nvidia-re), [benchmark reliability issue](https://github.com/juv4uk/gp107-nvidia-re/issues/28).

## 6. Що ще невідомо / потребує owner-approved перевірки

- Точна ревізія GA-H170-Gaming 3 та точний PCI ID Killer Ethernet.
- Фактичний codec ID HDA; ALC1150 підтверджений лише специфікацією плати.
- Фізичний Linux driver binding для кожного пристрою, firmware load stages, suspend/resume, audio/network/storage I/O.
- NVK enumeration та GP107 runtime A/B. За gp107-nvidia-re #18 потрібен окремий explicit owner approval до Vulkan enumeration/channel init/submit/reboot.
- Повна Guix system build/ISO closure та physical boot на H170.

До виконання цих перевірок manifest зберігає `not-assessed`, `unknown` та `not-run`; не перетворює package/config evidence на hardware certification.
