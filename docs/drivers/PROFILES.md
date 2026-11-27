# Профілі драйверів і firmware

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

## Призначення

Каталог містить окремі машиночитані профілі для конкретної reference-машини H170-Gaming 3. Це реєстр доказів і кандидатів, а не список гарантій сумісності й не автоматичний пакет для встановлення.

- drivers/profiles/h170-free.json — базовий вільний профіль.
- drivers/profiles/h170-compatibility.json — окремий opt-in запис кандидата NVIDIA 580.x для Pascal. Він не вмикає й не розповсюджує драйвер.
- drivers/schema/profile.schema.json — JSON Schema Draft 2020-12.

## Рівні доказів

Поля навмисно розділяють етапи, які не можна зводити до одного прапорця:

1. package_resolution — чи знайдено пакет у конкретному pinned Guix channel.
2. kernel_config — чи драйвер вбудований або доступний як модуль у конкретному ядрі.
3. live_rootfs, initrd, installed_rootfs — чи є потрібні файли саме на відповідному етапі завантаження/роботи.
4. runtime_binding і runtime_load — чи драйвер реально прив'язався до пристрою та чи завантажив потрібне firmware.
5. functional_validation — окремий тест функції пристрою в названому середовищі.

not-assessed означає, що перевірки ще не було. unknown означає, що наявних даних недостатньо. Ні те, ні інше не означає ані успіх, ані помилку.

## Зв'язок із evidence bundle WSM

Цей manifest — каталог кандидатів і стадій інтеграції драйвера; він не є
підтвердженням функціональної сумісності. Загальний контракт
[`wsm-profile-evidence/2`](../HARDWARE-PROFILE-EVIDENCE.md) має іншу
роль: прив'язує точні bytes hardware report і `profile.scm`, а кожен
функціональний `pass`/`fail` — до окремого hashed functional-test
artifact. Не зливайте ці схеми в одну й не підвищуйте статус manifest
через сам факт наявності evidence bundle.

Поточні H170 manifests навмисно лишаються `profile_status: draft`:
channel lock не доводить package resolution/build; Windows PCI identity
не доводить Linux binding; перелік candidate packages не доводить
firmware в live rootfs/initrd; жоден functional test не позначений
`pass`. Інтеграція з installer можлива лише після окремої реалізації
та acceptance policy, що споживає обидва контракти.


## Початковий H170 target

Фізичний профіль із juv4uk/wsm-os/docs/OWNER-HARDWARE-PROFILE.md, повторно перевірений 2026-09-02, описує Gigabyte H170-Gaming 3 / Intel Core i5-6400 / Intel HD Graphics 530 / NVIDIA GTX 1050 Ti Pascal / Killer E2200 / Kingston NVMe / Samsung SATA / HDA audio.

Профіль джерела є Windows-observed і закріплений на [wsm-os@40ef00079d478d43fa496ec066bb96ac4c0850a3](https://github.com/juv4uk/wsm-os/blob/40ef00079d478d43fa496ec066bb96ac4c0850a3/docs/OWNER-HARDWARE-PROFILE.md). Для NVIDIA GeForce GTX 1050 Ti Windows PnP зафіксував vendor:device ID `10de:1c82` (`VEN_10DE DEV_1C82`, subsystem `SUBSYS_33511462`); це є доказом ідентичності пристрою у Windows, але не Linux driver binding. BDF `00000000:01:00.0` — лише адреса пристрою на шині й не є PCI ID. Для інших адаптерів PCI IDs не вигадуються та залишаються порожніми до read-only Linux inventory на фізичній машині. Wi-Fi та Bluetooth не підтверджені й залишаються `unobserved`. Windows identity сама по собі не доводить наявність Linux-модуля, firmware у rootfs/initrd, runtime binding чи функціональність.

## Provenance джерел і каналів

- **Free:** `channels.lock.scm` фіксує лише офіційний Guix channel `4e5195be20d9b124df8a8bb69213412236e4668e`. Для нього записано authenticated pull/channel introduction, але package query, system evaluation, build та ISO не виконані.
- **Compatibility:** `channels/compatibility.lock.scm` окремо фіксує Guix `4e5195be20d9b124df8a8bb69213412236e4668e` і Nonguix `6b8897cd6f3223b158c070cdc9cc638279f8c337`. Структурна наявність цих revisions у lock не є доказом криптографічної автентифікації: її ще треба виконати через pinned `guix time-machine`; тому маніфест чесно ставить `channel_authentication_evidence: not-evaluated`.
- **Owner hardware evidence:** обидва профілі посилаються на незмінний snapshot [`wsm-os@40ef00079d478d43fa496ec066bb96ac4c0850a3`](https://github.com/juv4uk/wsm-os/blob/40ef00079d478d43fa496ec066bb96ac4c0850a3/docs/OWNER-HARDWARE-PROFILE.md). У ньому BIOS F22e та UEFI спостережені у Windows; Secure Boot лишається `unknown`.
- Channel revisions — лише identity inputs. Вони не доводять package resolution, kernel configuration, firmware у rootfs/initrd, runtime binding чи функціональність.


## Оновлені upstream-орієнтири для GTX 1050 Ti (2026-11-26)

Ці довідки уточнюють покоління-кандидати, але не підвищують жоден runtime/build статус у маніфестах:

- **Вільний шлях Nouveau/NVK:** актуальна [документація Mesa NVK](https://docs.mesa3d.org/drivers/nvk.html) вказує Kepler і новіші покоління, Vulkan 1.4 для офіційно підтриманих GPU та мінімальне ядро Linux 6.6. Документація окремо попереджає, що developer-only override може відкрити навіть погано перевірені або зламані GPU. Це не доводить роботу PCI ID `10de:1c82`, Guix-пакета чи KDE acceleration на H170.

- **Compatibility-шлях NVIDIA:** NVIDIA визначає Linux 580.x як останню Unix-гілку для Pascal ([строки підтримки](https://nvidia.custhelp.com/app/answers/detail/a_id/3142/kw/windows%20supported/related/1)). Для Pascal потрібен proprietary kernel-module flavor; відкриті NVIDIA kernel modules доступні лише для Turing і новіших поколінь ([офіційний посібник](https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/610/kernel-modules.html)). Не підміняти цю залежність open-module пакетом.

Станом на 2026-11-26 офіційна сторінка Linux 580.196.11 (реліз 23.11.2026) прямо перелічує GeForce GTX 1050 Ti у Supported Products: [NVIDIA 580.196.11](https://www.nvidia.com/en-us/drivers/details/285683/). Це лише product-list evidence; pinned Nonguix revision не означає, що package version дорівнює 580.196.11.

Це лише upstream references. У профілях навмисно залишаються `package_resolution: not-assessed`, `kernel_config: not-assessed`, `runtime_binding: unknown`, `functional_validation: not-run` та невизначені license/redistribution. Наступний доказ — точний Guix package/closure і ABI на зафіксованому channel; після цього окремо потрібні image/rootfs/initrd inspection та фактичний тест. Не використовувати developer override як production acceptance.

## Окремий шлях оцінювання та збірки Compatibility

Compatibility не можна перевіряти через Free lock. Для нього є окремі Make targets,
які завжди передають `channels/compatibility.lock.scm` до `guix time-machine`:

| Команда | Що доводить | Чого не доводить |
| --- | --- | --- |
| `make describe-compatibility-lock` | Guix може розв'язати pinned Guix + Nonguix channels із перевіркою автентичності за замовчуванням | package resolution, build або роботу пристрою |
| `make check-compatibility-eval` | structural lock policy, channel resolution та успішний `guix system build ... --dry-run` для `systems/live-compat.scm` | що derivations побудовані або образ завантажується |
| `make build-compatibility-system` | повну побудову system derivation у Guix store | ISO image, BIOS/UEFI boot чи фізичну роботу NVIDIA |
| `make image-live-compat` | побудову Compatibility ISO через той самий lock-aware `scripts/build_iso.sh`, із manifest та SHA-256 | BIOS/UEFI/QEMU acceptance або фізичну функціональність GPU |

Приклад послідовності після commit у чистому checkout:

```sh
make describe-compatibility-lock
make check-compatibility-eval
make build-compatibility-system
WSM_ISO_DIR="$PWD/build/compatibility-$(git rev-parse --short HEAD)" make image-live-compat
```

`scripts/build_iso.sh` відмовляється працювати з dirty worktree, повторно
використовувати попередні output files або вимикати channel authentication.
Для наступної спроби задавайте новий порожній `WSM_ISO_DIR`; не видаляйте
попередні build logs до розбору результату.

Ці targets навмисно **не входять** до `make check`, Free Minimal release workflow
або default image target. Вони потребують Guix, часу та дискового місця для
окремого opt-in Compatibility closure. Навіть успішний `build-compatibility-system`
чи `image-live-compat` не змінює manifest status на functional pass:
після build окремо потрібні BIOS/UEFI QEMU smoke, перевірка rootfs/initrd,
а для твердження про GTX 1050 Ti — дозволена фізична перевірка на H170.
Жодна з цих команд не запускає `guix system init`, не змінює фізичний диск,
EFI/NVRAM або firmware хоста.

## Валідація

Запустити:

    python3 tests/test_driver_profiles.py

До інтеграції у Live ISO потрібно заповнити кожне поле реальним результатом pinned package query/build, перевірити rootfs/initrd окремо та зберегти точні логи/версії. Для функціонального статусу потрібен окремий QEMU або дозволений physical test; QEMU/WSL не доводять binding на фізичному H170.

## Межі безпеки

Профілі не виконують firmware update, не завантажують модулі, не монтують/форматують диски та не змінюють EFI. `profile_class: free` і `enabled_by_default: true` описують клас та політику ввімкнення, а не підтверджують Free-сумісність кожного пакета. Для неперевірених кандидатів `source_license` лишається `unknown`, а `package_resolution` — `not-assessed`, доки пакет не перевірено на точній ревізії з `channels.lock.scm` і не завершено окремий license review. Free profile не містить Nonguix або proprietary components. Compatibility profile вимкнений за замовчуванням; ліцензія, ABI, походження та право розповсюдження NVIDIA package залишаються unknown до окремого review.

## Наявний system-level Compatibility профіль

`systems/compatibility.scm` тепер існує в `main` як окремий opt-in рецепт Nonguix/NVIDIA `nvda-580`. Це не робить H170 compatibility manifest buildable: наявний `channels.lock.scm` фіксує лише офіційний Guix, а recipe потребує `(nonguix transformations)` і `(nongnu packages ...)`. Окремий `channels/compatibility.lock.scm` уже фіксує Guix + Nonguix commits та introduction fingerprints, але його криптографічну автентифікацію ще не виконано. Тому package resolution/build/redistribution у H170 Compatibility лишаються `not-assessed`/`unknown`. Free profile та основний `systems/live.scm` не повинні імпортувати Compatibility чи Nonguix.



## GP107 Pascal: окрема перевірка мікропрограми

Для NVIDIA GTX 1050 Ti (GP107) не можна робити висновок, що сам відкритий
модуль ядра автоматично забезпечує повноцінне 3D-прискорення та обчислення
без мікропрограми.

У відкритій реалізації Nouveau:
- [gp107.c](https://codebrowser.dev/linux/linux/drivers/gpu/drm/nouveau/nvkm/engine/gr/gp107.c.html)
  оголошує залежності графічного рушія від мікропрограм FECS/GPCCS та
  файлів контексту GR.
- [gm200.c](https://codebrowser.dev/linux/linux/drivers/gpu/drm/nouveau/nvkm/engine/gr/gm200.c.html)
  завантажує FECS і GPCCS через механізм ACR; резервна функція
  `gm200_gr_nofw()` повідомляє про відсутню мікропрограму та повертає
  `-ENODEV`.

Отже, для ініціалізації графічного рушія GP107, потрібного для 3D та
обчислень, необхідні відповідні файли мікропрограми. Linux-libre без цих
невільних файлів не можна називати повноцінно прискореним стеком GP107
для 3D та обчислень. Це **не доводить**, що базовий вивід зображення
та KMS також неможливі без мікропрограми GR: підтримку дисплея потрібно
перевіряти окремо.

Важливо розрізняти:
- мікропрограму, яку дозволено поширювати за окремою ліцензією виробника;
- вільну мікропрограму з доступним для змін вихідним кодом;
- незалежну відкриту реалізацію мікропрограми.

Сам факт присутності файлів NVIDIA у linux-firmware не робить їх
вільним програмним забезпеченням. Перш ніж заявляти про повністю вільне
прискорення GP107, потрібно довести законний і технічно реалістичний
шлях незалежної відкритої реалізації. Не обходити ланцюжок перевірки
підпису ACR і не змінювати статуси мікропрограми без окремих доказів.

### Ліцензійні обмеження мікропрограми NVIDIA

У поточному [linux-firmware WHENCE](https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware/+/refs/heads/main/WHENCE)
групу мікропрограм GP107 для Nouveau позначено як таку, що дозволена
до поширення за умовами `LICENCE.nvidia`. Це дозвіл на поширення за
окремими умовами, а не вільна ліцензія з правом змінювати мікропрограму.

[LICENCE.nvidia](https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware.git/+/133355e89e7f0ab5d61e51eaeda6166c1bb3deb3/LICENCE.nvidia)
містить обмеження щодо зворотного аналізу, декомпіляції, дизасемблювання
та перекладу мікропрограми. NVIDIA публікує аналогічні обмеження у
[ліцензії драйвера Linux](https://www.nvidia.com/en-us/drivers/nvidia-license/).
Це умови ліцензії виробника; їхній вплив разом із можливими
законодавчими винятками для сумісності потрібно оцінювати окремо
відповідно до застосовного права. Не можна автоматично вважати, що
сам факт володіння відеокартою скасовує ці умови.

Практичний наслідок для WSM: не включати ці файли до вільного профілю
та не перетворювати дослідження REA на декомпіляцію, переклад або обхід
ACR без попередньої правової оцінки. Дослідження можна продовжувати
через відкритий код upstream, публічні специфікації, незалежні
спостереження за обладнанням і власну реалізацію в межах підтверджених
прав. Якщо колись знадобиться шлях із дозволеною до поширення
мікропрограмою, він має бути окремим необов'язковим профілем із
відповідною ліцензією.

Це обмеження не робить профіль H170 функціонально перевіреним:
`runtime_binding`, розв'язання пакетів, наявність мікропрограми на
етапах завантаження та `functional_validation` залишаються окремими
непідтвердженими станами.


## Intel HD Graphics 530 (Skylake): DMC, GuC та HuC

Для Skylake i915 потрібно розрізняти базову графіку та функції
мікроконтролерів:
- **DMC** керує станами дисплейного рушія з низьким енергоспоживанням.
  У [upstream i915](https://code.googlesource.com/linux/torvalds/linux/+/69ffab9b9e698248cbb4042e47f82afb00dc1bb4/drivers/gpu/drm/i915/display/intel_dmc.c)
  відсутність мікропрограми DMC призводить до вимкнення керування
  живленням під час роботи. Це не є доказом, що базова графіка або KMS не працюватимуть.
- **GuC** не є обов'язковим для базової роботи драйвера; він може
  забезпечувати планування графічних контекстів і керування живленням.
  **HuC** потрібен лише для окремих медіаможливостей. Див.
  [документацію i915](https://docs.kernel.org/6.18/gpu/i915.html).
- Linux-firmware [WHENCE](https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware/+/refs/heads/main/WHENCE)
  перелічує Skylake DMC/GuC firmware під Intel LICENSE.i915.
  Ця ліцензія дозволяє лише незмінене бінарне поширення та забороняє
  зворотний аналіз, декомпіляцію та дизасемблювання:
  [LICENSE.i915](https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware/%2B/refs/tags/20250211/LICENSE.i915).

Для вільного профілю це означає: i915 можна оцінювати як відкритий
драйвер, але повноцінне керування живленням дисплея через DMC не можна
заявляти без відповідної мікропрограми. GuC/HuC оцінюються окремо
за конкретними функціями. У H170 manifest firmware позначено
`optional` для базової графіки та `nonfree` за ліцензією; це не
підвищує package, runtime або functional-validation statuses.


### Як читати firmware.redistribution у Free manifest

Поле `firmware.redistribution` описує відомий клас ліцензії
мікропрограми, а не факт її включення до образу. Тому Free manifest
може чесно позначити відому залежність як `nonfree`, водночас залишаючи
`package_candidates: []`, `package_resolution: not-assessed` і всі
стадії присутності/завантаження непідтвердженими. Саме
`policy.nonfree_components_included: false` та відсутність package
candidates гарантують, що відома невільна мікропрограма не стає частиною
Free closure. Не приховуйте невільну залежність значенням `unknown`,
якщо її ліцензія вже встановлена.


## Інші H170 пристрої: де host firmware не потрібна

Статичний огляд поточного upstream-коду дає такі попередні висновки:

- **Killer E2200 / `alx`:** у каталозі upstream-драйвера немає
  `request_firmware` або `MODULE_FIRMWARE`; отже, host-loadable
  мікропрограма драйверу не потрібна. Таблиця PCI ID містить E2200;
  LKDDb зіставляє його з `1969:e091`. Власний hardware profile
  підтверджує модель E2200, але не точний PCI ID — поле `pci_ids`
  залишається порожнім до окремого спостереження.
- **HDA audio:** звичайний codec path не потребує vendor firmware.
  Окремий `snd-hda-patch-loader` може завантажити необов'язковий
  користувацький псевдо-firmware patch для ініціалізації. Це не
  обов'язкова залежність базового драйвера. Точний codec ID, зокрема
  можливий ALC1150, ще не підтверджений.
- **NVMe та AHCI/SATA:** generic host drivers не вимагають firmware
  blob для звичайної роботи контролера. Внутрішня firmware SSD/HDD
  належить самому накопичувачу й не є host firmware package, яке Guix
  має завантажувати; її версія/оновлення не перевірялися.
- **USB/xHCI:** generic host controller path окремо перевіряється
  у source audit; це не є доказом наявності конкретних USB-периферій.

Ці висновки стосуються залежності host driver від зовнішньої firmware.
Вони не доводять package resolution, kernel config, фізичне binding,
мережевий трафік, звук, storage I/O чи suspend/resume. У manifest
відповідні стани лишаються окремими й непідтвердженими.


## Intel Core i5-6400: BIOS microcode та раннє оновлення ОС

Для точного CPUID `0x000506E3` (i5-6400) власне дослідження BIOS
F22e у [wsm-os](https://github.com/juv4uk/wsm-os/blob/main/hardware/bios-f22e/FIT-AND-STRUCTURE-ANALYSIS.md)
підтвердило:
- BIOS містить мікрокод ревізії `0xC2` від 2017-11-16;
- UEFI-проба до запуску ОС побачила саме `0xC2`;
- Windows після завантаження повідомляє `0xD6` від 2019-10-03.

Отже, Linux-libre без зовнішнього Intel microcode package **не означає
відсутність мікрокоду**: CPU стартує з `0xC2`, уже наданого BIOS.
Але без раннього оновлення ОС профіль не повторює підтверджену Windows
ревізію `0xD6`. Ядро Linux підтримує раннє завантаження мікрокоду з
initrd за шляхом `kernel/x86/microcode/GenuineIntel.bin`; див.
[документацію Linux microcode loader](https://www.kernel.org/doc/html/next/x86/microcode.html).

Офіційний [Intel microcode repository](https://github.com/intel/Intel-Linux-Processor-Microcode-Data-Files)
постачає мікрокод як бінарні оновлення. Його
[ліцензія](https://github.com/intel/Intel-Linux-Processor-Microcode-Data-Files/blob/main/license)
дозволяє лише незмінене бінарне поширення та забороняє зворотний
аналіз, декомпіляцію й дизасемблювання. Тому цей пакет класифіковано
як `nonfree`; він не входить до WSM Free closure. Ревізію мікрокоду
потрібно записувати в benchmark metadata, оскільки вона може впливати
на errata, безпеку та відтворюваність результатів. Не застосовувати
late-load і не досліджувати бінарний blob декомпіляцією.


## Guix channel: NVK уже ввімкнений у Mesa для x86_64

У зафіксованому каналі Guix, commit
`4e5195be20d9b124df8a8bb69213412236e4668e` від 2026-11-25:
- [gnu/packages/gl.scm](https://codeberg.org/guix/guix/src/commit/4e5195be20d9b124df8a8bb69213412236e4668e/gnu/packages/gl.scm)
  визначає Mesa 26.2.6; для x86_64 передає
  `-Dvulkan-drivers=amd,intel,intel_hasvk,nouveau,swrast,virtio`
  та додає Cargo inputs для Mesa. Отже NVK уже ввімкнений у package recipe.
- [gnu/packages/linux.scm](https://codeberg.org/guix/guix/src/commit/4e5195be20d9b124df8a8bb69213412236e4668e/gnu/packages/linux.scm)
  визначає типовий `linux-libre` як 7.3.5.
- [Документація NVK](https://docs.mesa3d.org/drivers/nvk.html)
  вказує мінімальне ядро Linux 6.6.

Отже, не потрібно форкувати Mesa або створювати окремий Guix recipe
лише для ввімкнення NVK на x86_64. Але це **не** доводить успішну
збірку конкретного WSM system closure, встановлення ICD, runtime
binding або функціональність GP107. Головна перешкода Free-профілю
залишається окремою: GP107 GR потребує FECS/GPCCS firmware, яке має
невільну ліцензію та проходить через ACR.
