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
| [hwloc 2.16.0 stable (19.11.2026)](https://www.open-mpi.org/software/hwloc/v2.16/) | Ієрархія CPU/cache/NUMA/CXL та locality PCI/I/O-пристроїв; XML topology export. Офіційний архів: SHA-256 `ad05eb466b915a4f0e0228173d7e09974ac38760c38d5b6f060254c050fca12d` | У звичайному API I/O discovery вимкнено; `lstopo` сканує ширше і може бути повільним. Для PCI bus details може знадобитися libpciaccess; не описує USB interface binding або GPU→DRM connector→monitor. OS/logical indexes не є сталими hardware IDs | Опційний provider для CPU↔NUMA↔PCI locality, не заміна зв'язків #18 |
| [libdisplay-info 0.4.0](https://gitlab.freedesktop.org/emersion/libdisplay-info) | EDID/DisplayID decode; реліз додав DisplayID v1 Type IV timings та DisplayID v2 CTA-861 blocks | Advertised timing не є KMS-exposed mode, active mode або functional pass. High-level API краще ізолює споживача від змін low-level API | Опційний parser у display lane поруч із kernel DRM/KMS observations |
| [drm_info 2.10.0](https://gitlab.freedesktop.org/emersion/drm_info) | Локальний DRM device/property inventory, JSON output через `drm_info -j` | JSON може містити GPU/monitor identifiers; output/version contract треба pin-ити. Не доводить, що режим реально працює або що монітор фізично підключений до конкретного GPU без явного topology edge | Опційний локальний DRM provider; без upload у DRM database |
| [systemd hwdb 262](https://www.freedesktop.org/software/systemd/man/262/hwdb.html) | Локальне зіставлення modalias-подібних ключів із udev property/value metadata; підтримує окремий query шлях | Нормалізація назви/властивостей не доводить driver binding, runtime firmware load чи роботу пристрою | Допоміжний шар назв і quirks, не compatibility oracle |
| [PCIe AER sysfs counters](https://github.com/torvalds/linux/blob/master/Documentation/ABI/testing/sysfs-bus-pci-devices-aer) | Correctable, non-fatal та fatal PCIe error counters для AER-capable пристроїв: `aer_dev_correctable`, `aer_dev_nonfatal`, `aer_dev_fatal` і root-port totals | Лічильники означають помилки «as seen/reported» відповідним компонентом. Endpoint-проблема може інкрементувати link partner/root port, а endpoint — показувати нуль. Відсутність файла не означає нуль | Додаткове read-only спостереження про PCIe link/error history з BDF джерела та timestamp |
| [devlink health](https://docs.kernel.org/6.19/networking/devlink/devlink-health.html) | `devlink health show` може показати status/config зареєстрованих драйвером health reporters для NIC/switch/accelerator | Покриття залежить від драйвера. `diagnose` викликає driver callback і має admin-only netlink permission; `dump show` може згенерувати новий dump; `recover`, `test`, `set`, `dump clear` не є пасивними | Лише опційний status query через `show`; інші команди — окремий consent-based support mode |
| [VKMS](https://docs.kernel.org/gpu/vkms.html) + [IGT GPU Tools](https://gitlab.freedesktop.org/drm/igt-gpu-tools) | Віртуальний DRM/KMS display для headless CI/VM перевірок | Для VKMS потрібно завантажити модуль/налаштувати configfs; IGT може вимагати окремої сесії без compositor-а. Це змінює стан тестового kernel і не є live preflight | Ізольована CI/VM lane, не probe на фізичному ПК |
| [fwupd HSI](https://fwupd.github.io/hsi.html) | Окремі показники firmware/platform security posture | Security posture не доводить наявність runtime firmware blob, успішне виконання `request_firmware()` чи ініціалізацію пристрою | Окремий security report; не змішувати з #16 compatibility evidence |

## hwloc 2.16.0 — статус stable та режим використання

Офіційна сторінка Open MPI позначає `2.16.0` як **stable release**, опублікований 19.11.2026. Для архіву `hwloc-2.16.0.tar.bz2` наведено SHA-256 `ad05eb466b915a4f0e0228173d7e09974ac38760c38d5b6f060254c050fca12d`. Це вже не release candidate.

Для WSM особливо важливі дві межі з офіційної документації:
- Звичайний hwloc API за замовчуванням не включає I/O objects; їх потрібно явно вмикати відповідним topology flag/provider.
- `lstopo` вмикає майже всі discovery features за замовчуванням, включно з I/O і зовнішніми providers, тому може бути значно повільнішим. Для контрольованого inventory треба задавати мінімальний набір компонентів і вимірювати час/closure size.

hwloc logical indexes зручні для відображення ієрархії всередині snapshot, але не слід використовувати їх як стійкі hardware IDs. В офіційному FAQ зазначено, що OS/physical indexes можуть бути непослідовними й змінюватися після BIOS/system update; WSM має тримати власні report-local IDs і джерельні bus locators.

## Безпека EDID/DisplayID parser-а — обов'язкова умова

Реліз `libdisplay-info 0.4.0` додав корисну підтримку DisplayID v1 Type IV timings і DisplayID v2 CTA-861 blocks, але **не можна вважати його безпечним baseline для live image**. Станом на 25.11.2026 публічні записи описують два out-of-bounds read дефекти в parser-ах DisplayID:

- [CVE-2026-112271](https://access.redhat.com/security/cve/cve-2026-112271) — DisplayID v1 parser може читати за межами heap buffer, коли довжина data block виходить за межі секції.
- [CVE-2026-112272](https://access.redhat.com/security/cve/cve-2026-112272) — аналогічний вихід за межі буфера в DisplayID v2 parser.

Умовою атаки може бути спеціально сформований EDID з фізичного дисплея/адаптера або з локального файла; описані наслідки — аварійне завершення застосунку (DoS), не підтверджене виконання коду. Red Hat та OSV позначають уражені версії включно з 0.4.0. У досліджених джерелах на цю дату не підтверджено виправлений upstream release; не стверджувати, що 0.4.1 або інша patched версія вже існує, без повторної перевірки.

Практичні вимоги до WSM:

- Не додавати `libdisplay-info <= 0.4.0` до live image або обов'язкового preflight dependency.
- Перед інтеграцією перевірити upstream fix/реліз, дистрибутивні security advisories та фактичну версію залежності в pinned Guix/Nix closure.
- Поки виправлення не підтверджено, залишити EDID parsing необов'язковим і пропускати його без блокування inventory. Не парсити неперевірений EDID у привілейованому процесі.
- Для `drm_info` перевіряти, чи його build лінкований із `libdisplay-info`; якщо так, застосовувати ті самі обмеження. JSON режим може містити EDID bytes у base64, тому raw JSON не можна експортувати як privacy-safe результат.
- Kernel DRM/KMS connector properties і kernel-exposed modes залишаються окремим джерелом. Відкладання userspace EDID parser-а не повинно перетворювати відсутні parsed fields на негативний verdict.

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

- [hwloc v2.16.0 stable release](https://www.open-mpi.org/software/hwloc/v2.16/) — офіційний stable archive від 19.11.2026, SHA-256 та можливості CPU/NUMA/I/O locality.
- [hwloc v2.16.0 FAQ](https://www.open-mpi.org/projects/hwloc/doc/v2.16.0/faq.html) — default I/O filtering, lstopo discovery cost та нестабільність OS indexes.
- [hwloc I/O device documentation](https://hwloc.gitlabpages.inria.fr/doc-snapshots/v2.x-html/a00369.html) — фільтри I/O discovery та залежність від підтримки ОС/libpciaccess.
- [libdisplay-info 0.4.0 release announcement](https://mail-archive.com/wayland-devel%40lists.freedesktop.org/msg44365.html) — DisplayID v1/v2 coverage та API compatibility notes.
- [drm_info 2.10.0 package record](https://openmamba.org/en/rpms/base/drm_info/) — version, MIT license та build requirements; upstream source вище.
- [systemd hwdb 262 manual](https://www.freedesktop.org/software/systemd/man/262/hwdb.html) — modalias-like mapping і query semantics.
- [Linux PCIe AER sysfs ABI](https://github.com/torvalds/linux/blob/master/Documentation/ABI/testing/sysfs-bus-pci-devices-aer) та [AER implementation](https://github.com/torvalds/linux/blob/master/drivers/pci/pcie/aer.c).
- [Linux devlink health](https://docs.kernel.org/6.19/networking/devlink/devlink-health.html), [netlink specification](https://docs.kernel.org/netlink/specs/devlink.html), [devlink-health(8)](https://manpages.debian.org/unstable/iproute2/devlink-health.8.en.html).
- [Linux VKMS](https://docs.kernel.org/gpu/vkms.html) — software-only KMS testing in isolated VM/CI.
- [fwupd HSI](https://fwupd.github.io/hsi.html) — platform security posture, a separate evidence category.

## Висновок

Першими для реального WSM експерименту варто оцінити `libdisplay-info`, `drm_info`, `hwloc` та read-only PCIe AER counters. `devlink health show` — optional support for selected NIC/accelerator drivers. VKMS/IGT — тільки CI/VM. fwupd HSI — окремий security pane.

Ні один із цих інструментів не повинен самостійно виставляти загальний verdict сумісності. WSM має зберігати первинний факт, джерело, час, обмеження та невідомі стани окремо від policy decision.
