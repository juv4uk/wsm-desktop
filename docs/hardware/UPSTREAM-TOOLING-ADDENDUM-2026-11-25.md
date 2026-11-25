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

## Security gate: EDID/DisplayID parser не можна додавати без перевірки CVE

EDID/DisplayID надходить від зовнішнього пристрою або з локального файла і має трактуватися як недовірений вхід. Для `libdisplay-info` оприлюднено два дефекти читання за межами буфера в DisplayID parser-ах:

- [CVE-2026-112271](https://access.redhat.com/security/cve/cve-2026-112271) — DisplayID v1 parser може читати за межами секції, коли оголошена довжина data block перевищує її межі.
- [CVE-2026-112272](https://access.redhat.com/security/cve/cve-2026-112272) — відповідний out-of-bounds read у DisplayID v2 parser.

Security advisories описують спеціально сформований EDID від дисплея/адаптера або з файла та можливе аварійне завершення процесу (DoS). AWS advisories додатково вказують affected versions through 0.4.0 для відповідних parser-ів: [112271](https://explore.alas.aws.amazon.com/CVE-2026-112271.html), [112272](https://explore.alas.aws.amazon.com/CVE-2026-112272.html). Це не підтверджує, що всі дистрибутивні збірки однаково уражені: vendor backport/patch статус треба перевіряти за конкретним пакунком і ревізією.

Практичні вимоги WSM:

- Не включати upstream `libdisplay-info 0.4.0` як обов'язковий компонент live image та не запускати його parser у привілейованому процесі, доки не підтверджено виправлений upstream commit/release або дистрибутивний backport.
- Перед прийняттям будь-якої версії перевіряти security advisory, changelog/fix commit і фактичний package source у pinned Guix/Nix channel. Сам номер версії без перевірки backport недостатній.
- Залишити EDID/DisplayID decoding опційним. За відсутності безпечного parser-а не збирати parsed identity/timing fields; не блокувати базовий hardware inventory і використовувати окремі kernel DRM/KMS connector/mode observations.
- Перевірити dependency closure `drm_info`: наприклад, пакетний запис FreeBSD для 2.10.0 показує залежність від `libdisplay-info 0.4.0` ([package dependency record](https://portstatus.bsdproject.de/graphics/drm_info/)). Це приклад конкретного пакування, а не доказ такого самого closure в Guix/Nix.
- Не вважати JSON `drm_info` автоматично privacy-safe: якщо в ньому є EDID/base64 або повні display identifiers, санітизувати їх до включення у WSM report/export.

До підтвердження безпечного parser-а WSM має зберігати різницю між "EDID доступний у sysfs", "EDID успішно розібраний" та "KMS експонує mode". Відсутність parsed EDID полів — це `unknown/not-collected`, а не несумісність дисплея.

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
