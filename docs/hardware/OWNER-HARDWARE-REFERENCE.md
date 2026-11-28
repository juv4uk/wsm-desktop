# Gigabyte GA-H170-Gaming 3

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **дослідницька довідка, не hardware evidence bundle; не перевірено `wsm-hwcheck`**
- Джерело: [`wsm-os/docs/OWNER-HARDWARE-PROFILE.md`](https://github.com/juv4uk/wsm-os/blob/main/docs/OWNER-HARDWARE-PROFILE.md) (знімок від 2026-08-29, жива повторна перевірка 2026-09-02)
- Ревізія материнської плати: **unknown** — Windows CIM повертав `x.x`; F22e існує для кількох ревізій, але це не визначає ревізію конкретної плати
- `evidence.json`: **немає**, і саме тому цей профіль не бере участі в інсталяції

## Чому це довідка, а не evidence bundle

Дані нижче — датовані спостереження Windows і WSL, зроблені в іншому проєкті.
Вони корисні для планування тестів, але це **не** доказ у сенсі
[HARDWARE-PROFILE-EVIDENCE.md](../HARDWARE-PROFILE-EVIDENCE.md):
немає `report_id` від `wsm-hwcheck`, немає переліку перевірених функцій, немає
того, що саме не працює.

Вигадати ці поля означало б зробити рівно те, проти чого існує формат. Тому
машина описана тут, а bundle з'явиться після першого прогону на ній.

## Що відомо

| Компонент | Значення | Джерело |
| --- | --- | --- |
| Плата | Gigabyte GA-H170-Gaming 3; ревізія невідома (`x.x`) | Windows CIM |
| Firmware | AMI BIOS F22e, 2018-03-09, UEFI | Windows CIM |
| CPU | Intel Core i5-6400, Skylake, 4C/4T, без SMT | WSL |
| ISA | WSL показав AVX, AVX2, FMA, BMI1/2, ADX, AES, POPCNT; це вхід для synthetic classifier test, не native Linux CPU evidence | WSL |
| Пам'ять | 16 GiB, 2×8 DDR4-2133 | Windows CIM |
| Графіка | Intel HD 530 + NVIDIA GTX 1050 Ti 4 GiB (Pascal, sm_61), PCI `01:00.0` | Windows + `nvidia-smi` |
| Мережа | Killer E2200 Gigabit Ethernet | Windows CIM |
| Накопичувачі | Kingston SNV2S1000G NVMe 1 TB; Samsung 850 EVO SATA 120 GB; Samsung HD321KJ HDD 320 GB | Windows CIM |

## Що з цього випливає для WSM

**ISA test не є hardware certification.** Тест у `tests/test_cpu_isa.py` перевіряє
класифікатор на синтетичному наборі прапорців, узятому з датованого WSL snapshot:
він демонструє, що цей набір відповідає `x86-64-v3`, а не підтверджує поточну
bare-metal capability через WSM. Остаточне значення має надати новий native
Linux `wsm-hwcheck` report на самій машині.

**Очікуваний Free graphics path — Intel i915/Mesa.** Windows/WSL snapshot
підтверджує ідентичність Intel HD 530, але не її native Linux driver binding,
DRM/KMS display path або Plasma session. Усе це лишається `not-assessed` до
перевірки з native Linux/live USB. NVIDIA GTX 1050 Ti — окремий Pascal
Compatibility candidate; це не доказ роботи `nvda-580` на цьому Guix lock.

**NVMe є, і він один.** Розбиття має це враховувати: `nvme0n1` потребує
суфікса `p` у назвах розділів, що покрито `device_for()` в
`wsm_install/install_steps.py`.

**Два різні накопичувачі SATA.** Інсталятор не повинен обирати ціль
самостійно — тільки явний вибір користувача.

## Чого бракує, щоб це стало профілем

1. Прогін `wsm-hwcheck` на самій машині й отримання `report_id`.
2. Заповнення `verified_functions`: що реально перевірено (графіка, звук,
   мережа, suspend).
3. Список того, що **не** перевірено — обов'язковий і непорожній.
4. `hardware_signature` з реальними PCI-ідентифікаторами.

Перший крок робить `scripts/draft_profile_evidence.py` після native Linux
`wsm-hwcheck`; решту — людина, яка виконувала контрольовані функціональні тести.
Не переносити Windows/WSL спостереження в `verified_functions` і не створювати
`evidence.json`, доки немає report ID, реальних artifact bytes та окремих
function-test результатів.


## Зовнішнє дослідження GP107 (окремий стенд; не сертифікація H170)

Станом на 2026-11-27 існує окреме дослідницьке сховище
[juv4uk/gp107-nvidia-re](https://github.com/juv4uk/gp107-nvidia-re), яке
містить clean-room probes, REA evidence та фізичні експерименти саме для
PCI ID `10de:1c82` (GP107 / GTX 1050 Ti). Його README описує тестовий
стенд як Kali Rolling 2026.3, kernel `7.2.15+kali-amd64` та NVIDIA
`580.196.11`, GPU на BDF `0000:01:00.0`.

**Не ототожнювати цей test host з H170 reference machine без окремого
доказу.** Збіг моделі GPU/PCI ID підтверджує релевантність результатів до
GP107, але не підтверджує материнську плату, BIOS, CPU, пам'ять, Guix
channel, Linux-libre чи повний склад саме цієї H170 конфігурації. Ці
матеріали є зовнішніми device-level research references, а не
`wsm-profile-evidence/2` і не змінюють статус жодного H170 manifest.

### Що вже доведено у GP107 research

- [Матриця можливостей](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/05-gp107-capability-matrix.md)
  розділяє runtime-proven, statically proven, interpretation та UNPROVEN.
  Вона не стверджує, що RM probes відкрили BAR0/MMIO або довели повний
  GPU command submission.
- [NVK compute result](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/14-nvk-vector-add-compute-result.md)
  фіксує один реальний vector-add compute run на окремому GP107 witness host.
  Водночас [документ надійності](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/18-procedural-deviation-and-benchmark-reliability.md)
  прямо фіксує, що погоджений source/BTF preflight не був повністю завершений
  до dispatch (**procedural deviation**). Тому це історичний device-level
  runtime fact, а не clean acceptance, поточний benchmark baseline чи доказ
  для H170; повторний експеримент потребує окремого owner-approved plan.
- [Порівняння NVK/NVIDIA](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/17-vulkan-compute-benchmark-open-vs-proprietary.md)
  має три повтори обох стеків, але було зняте до виправлень benchmark
  harness. [Документ надійності](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/18-procedural-deviation-and-benchmark-reliability.md)
  прямо позначає ці цифри як історичні, не як поточний acceptance baseline.
- [Надійна NVIDIA baseline](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/20-reliability-baseline-proprietary.md)
  дає median-of-three: 20,310 ns / 2.4201 GB/s для 4,096 елементів;
  1,267,551 ns / 9.9269 GB/s для 1 Mi; 10,616,000 ns / 9.4822 GB/s
  для 8 Mi. Це proprietary ICD 580.196.11 і HOST_VISIBLE|HOST_COHERENT
  шлях, а не VRAM bandwidth.
- [Матриця workgroup × batching](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/21-proprietary-performance-matrix.md)
  містить 108 успішних NVIDIA runtime points. Вона вказує на помітний
  submit overhead для малих задач і workload-залежний вплив local size.
- [DEVICE_LOCAL transfer/compute](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/22-device-local-transfer-and-compute-phases.md)
  містить виправлений command stream із memory dependencies для H2D →
  compute → D2H та `memoryTypeBits` validation у коді, але build,
  synchronization-validation і новий фізичний rerun ще не прийняті.
  Історичні 90.46 GB/s і 52.39 ms лишаються **EXPLORATORY / NOT ACCEPTED**
  і не можуть бути baseline чи доказом NVK/NVIDIA performance gap.

### Обмеження й незакриті питання

- Оновлений NVK A/B на виправленому benchmark harness ще не виконаний.
  docs/20–21 — NVIDIA-only baselines; docs/22 залишається EXPLORATORY / NOT
  ACCEPTED до виправлення synchronization; старе docs/17 не можна
  використовувати як остаточний NVK-vs-NVIDIA висновок.
- Canonical NVK acceptance harness — [GP107 PR #21](https://github.com/juv4uk/gp107-nvidia-re/pull/21),
  наразі Draft. Додаткові PR #23/#24 також Draft; не запускати паралельні
  harness-и.
- GP107 issue [#18](https://github.com/juv4uk/gp107-nvidia-re/issues/18)
  вимагає version-pinned Mesa 26.3.1 source audit, read-only host
  preflight та окремого explicit owner approval перед Vulkan enumeration
  або фізичним експериментом. Enumeration може створити тимчасові GR
  channel/VM/BO об'єкти; це не read-only операція. До такого дозволу
  не запускати `vulkaninfo --summary`, Vulkan enumeration, channel init,
  compute submit чи reboot.
- Офіційний [Nouveau thermal hwmon documentation](https://docs.kernel.org/driver-api/thermal/nouveau_thermal.html) описує read-only `temp1_input` там, де датчик експонується; це можна best-effort записувати до/після кожного повтору.
- `VK_KHR_pipeline_executable_properties` може надати shader executable statistics (instruction counts/spills тощо), якщо extension реально доступний на конкретному NVK runtime; це instrumentation candidate, не гарантія підтримки GP107.
- Офіційний [Nouveau feature status](https://nouveau.freedesktop.org/FeatureMatrix.html)
  зазначає, що reclocking доступний для деяких старіших поколінь та Turing+,
  але для GP10x Pascal існує firmware-signing обмеження. Це важливий
  performance ceiling для GP107, а не доказ несправності всього драйвера.
- Офіційна [Mesa NVK documentation](https://docs.mesa3d.org/drivers/nvk.html)
  описує покоління Kepler і новіші, але конкретний API version, features,
  performance та стабільність GP107 треба брати з version-pinned source
  і фізичних тестів, а не виводити з загального опису.

### Наслідки для WSM

1. Зберігати GP107 findings як зовнішні посилання; не копіювати harness
   або великі масиви raw logs у wsm-desktop.
2. Не підвищувати H170 profile statuses: package resolution, kernel config,
   firmware presence, runtime binding і functional validation лишаються
   `not-assessed` / `unknown` до H170-specific evidence.
3. docs/22 уже містить кодові виправлення memory dependencies та
   `memoryTypeBits`, але їх треба зібрати, перевірити synchronization
   validation і повторити workload на тому самому стенді. До прийняття
   нових артефактів історичні DEVICE_LOCAL числа не використовувати;
   причинність NVK/NVIDIA performance gap лишається UNPROVEN.
4. Не обіцяти універсальне перевершення NVIDIA. Спершу визначити workload,
   де WSM має виміряну перевагу; окремо документувати обмеження reclocking,
   power/clock control та відсутні функції.


## Пов'язана матриця firmware та microcode

Для зведеного огляду firmware, microcode, ліцензій і функціональних обмежень
див. [H170 firmware/capability matrix](H170-FIRMWARE-MATRIX.md).

## Актуалізація GP107: identity, UVM caller chain, firmware та FIFO evidence (2026-11-28)

Останній зовнішній GP107 REA snapshot на момент цього оновлення:
[juv4uk/gp107-nvidia-re @ `62a129608b57ca3d6cde1ca6d9beda0ba03130c5`](https://github.com/juv4uk/gp107-nvidia-re/tree/62a129608b57ca3d6cde1ca6d9beda0ba03130c5). Старі evidence-посилання нижче залишаються закріпленими на попередньому immutable snapshot `62a129608b57ca3d6cde1ca6d9beda0ba03130c5`, якщо сам звіт не оновлювався.
PR [#54](https://github.com/juv4uk/gp107-nvidia-re/pull/54) закрив production BAR-read шлях до доведення safe offset; [#55](https://github.com/juv4uk/gp107-nvidia-re/pull/55) зробив ASM load leaf private; [#56](https://github.com/juv4uk/gp107-nvidia-re/pull/56) закрив Pascal pinned-dirfd identity gap. Усі три merged; #53 закритий як superseded без merge. Exact-head static runs: #54 `46085676976`, #55 `46085947551`, #56 `46087161680` — success.

- **C11 API:** public `gp107_mmio_read32()` після opt-in, identity, driver-binding, BAR metadata та offset checks повертає `GP107_ERR_SAFE_OFFSET_UNPROVEN=21`. Production C path не відкриває `resource0` contents, не мапить BAR і не читає register. `stat(resource0)` у inventory — лише metadata про розмір.
- **Free Pascal API:** `Read32()` спершу отримує inventory, потім викликає `VerifyPinnedIdentity()` перед safe-offset refusal. Перевірка відкриває очікуваний BDF directory, тримає один fd і через нього звіряє `PCI_SLOT_NAME`, `PCI_ID`, `PCI_SUBSYS_ID`, vendor/device/revision, subsystem IDs, PCI config та driver binding (`readlinkat`). Дочірні sysfs-файли відкриваються через `openat(O_NOFOLLOW|O_NONBLOCK)` і перевіряються `fstat`. Public API завершується code 21 до будь-якого `resource0` content open / BAR mapping / load.
- **Pascal regression:** п’ять synthetic cases перевіряють bound, unbound (лише відсутній driver link), invalid driver entry, BDF symlink на інший BDF та same-BDF symlink на інший PCI ID. Exact-head run `46087161680` пройшов із pinned FPC 3.2.2, host-independent fail-closed gate, C/FPC compile та static tests. Це synthetic/software proof, не фізичний H170 test. Packed 140-byte inventory layout не змінено; `Load32Asm()` лишається поза public unit interface після #55.
- **UVM/BTF типи:** [docs/34](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/34-rea-p1-parent-object-and-test-context.md) та [docs/35](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/35-rea-p1-btf-type-proof.md) зіставляють інструкції з `.BTF` того самого shipped `nvidia-uvm.ko`: `g_uvm_global+0x28` = `parent_gpus[32]` (`uvm_parent_gpu_t *`), `parent+0x08` = `gpus[8]` (`uvm_gpu_t *`), `gpu+0x19f8` = `channel_manager` (`uvm_channel_manager_t *`). Розміри allocation `0x1d98` і `0xc228` збігаються з BTF типами `uvm_gpu_struct` і `uvm_parent_gpu_struct`.
- **`add_gpu` caller та аргументи ([docs/37](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/37-rea-p1-add-gpu-call-sites.md)):** доведено рівно два прямі `call add_gpu` — `0x0801eb42` і `0x0801ebf7`, обидва з `uvm_gpu_retain_by_uuid`. На цих call-site `rdi` є UUID-аргументом, `r8` — базою `parent->gpus[]`. Чотири `uvm_channel_manager_create` calls біля `0x080bad5a`, `0x080baeba`, `0x080bb1d0`, `0x080bb2d2` належать `uvm_test_channel_sanity`: це self-test path, не доведений production GPU-init path.
- **UUID chain від ioctl ([docs/38](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/38-rea-p1-register-gpu-uuid-chain.md)):** у shipped `nvidia-uvm.ko` доведено `uvm_api_register_gpu → uvm_va_space_register_gpu → uvm_gpu_retain_by_uuid → add_gpu`. UUID, переданий у `add_gpu`, береться з першого поля ioctl-параметра; на гілці `r8==0` слот `[rbp-0x118]` зберігає початковий `rdi`. Хто формує UUID у userspace та відповідність `BDF ↔ RM gpu_id` лишаються `UNPROVEN`.
- **`GetGpuInfo` call-site correction ([docs/37](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/37-rea-p1-add-gpu-call-sites.md)):** нове targeted Rizin observation виправляє другий `nvUvmInterfaceGetGpuInfo` call усередині `uvm_gpu_retain_by_uuid`: instruction починається в Rizin `0x0801eadb`, relocation у ELF `0x1a47c` вказує на поле `0x0801eadc`. Evidence `ev_580d64fc…` (`pd 14 @ 0x0801ead0`) і оновлений witness hash у GP107 master. Це уточнює static UVM call chain, але не встановлює userspace UUID producer, BDF ↔ RM `gpu_id` чи H170 runtime.
- **UUID direction through GetGpuInfo ([docs/40](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/40-rea-p1-gpu-info-uuid-direction.md)):** у shipped `nvidia-uvm.ko` доведено, що UUID передається як перший вхідний аргумент до `nvUvmInterfaceGetGpuInfo`; у `nvidia.ko` цей аргумент forwarded через `rm_gpu_ops_get_gpu_info` до `_nv046828rm`. Тому гіпотеза, що `nvUvmInterfaceGetGpuInfo` генерує UUID, відкликана (`retracted hypothesis`). Хто формує UUID у userspace і відповідність `BDF ↔ RM gpu_id` лишаються `UNPROVEN`; це окремий Kali/R580 статичний доказ, не H170 runtime.
- **Userspace UUID path ([docs/41](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/41-rea-p1-libcuda-userspace-uuid-source.md)):** у shipped `libcuda.so.580.196.11` (SHA-256 `20ad4403…`) статично простежено `device+0xc06` до payload єдиного цільового `ioctl(fd, 0x25, …)`, тобто `UVM_REGISTER_GPU`; `cuDeviceGetUuid` читає те саме поле. Це звужує шлях UUID у userspace, але **не** доводить, хто встановлює кінцевий callback `[holder+0x30]`, звідки походить значення чи відповідність `BDF ↔ RM gpu_id`. Build-ID/package pairing цієї `libcuda` із уже paired kernel modules також не завершено. Це статичний R580/Kali artifact evidence, не H170 runtime або H170 package evidence.
- **Зовнішній артефакт і межа тотожності:** BTF звіт pin-ить `nvidia-uvm.ko.xz` SHA-256 `80132204f76981b2373baeb936866347e3c80e8527feb118bffe03f6adc10e8f` та відновлений `.ko` SHA-256 `81b21527017a096f8276e7b93d04e82a414d03ac3b6a0831f9acba3a4ac488b6`. [docs/36 — pairing](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/36-r580-artifact-pairing.md) закриває provenance **на окремому Kali test host**: встановлені `.ko.xz`, DKMS outputs, розпаковані REA targets і завантажені `nvidia`/`nvidia_uvm` збігаються за package/version, `srcversion` і GNU Build ID. Це не доводить, що така сама package/kernel/module build pair стоїть на H170; H170-specific source pairing та native Linux inventory лишаються окремими.
- **Nouveau firmware dependency map ([docs/39](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/39-gp107-nouveau-firmware-dependency-map.md)):** source-only карта на Linux `f4585067150b85e33f60876149a6e742928da75e` та WHENCE snapshot показує GP107 GR FECS/GPCCS і software-context paths, shared GP102 ACR paths, SEC2 v0/v1 candidates та NVDEC scrubber. Це `SOURCE_CONFIRMED`/`SOURCE_CANDIDATE`, не доказ boot request/load, Guix closure/initrd/ISO presence чи pairing із завантаженим `nouveau.ko`. `LICENCE.nvidia` §2.1.2 вимагає, щоб firmware використовувалися на ОС, що розповсюджуються під OSI-approved open-source license, із незміненими binaries та копією ліцензії. Відповідно до злитого #586, WSM не включає й не перерозповсюджує ці blobs у Free або Compatibility channel/ISO до письмового owner/legal clearance для конкретної distribution model. Окрема невідповідність власних package license metadata WSM залишається відкритою в #367.
- **FIFO/non-stall evidence ([docs/09](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/09-gp107-fifo-nonstall-source-audit.md)):** окремий Kali Nouveau boot witness показав decoded `TOP_GR_RUNLIST_0_OBSERVED` для GR. Це не доводить, що конкретний GR/compute user channel прив'язаний до runlist 0, і не доводить `NONSTALL object registration / ALLOW / refcount`; статуси — `USER_CHANNEL_RUNLIST_UNCORRELATED / NONSTALL_SUBSCRIPTION_UNPROVEN`. Це зовнішній host, не H170 acceptance. Найменший наступний крок — read-only exact `nouveau.ko` ↔ kernel source/patchset pairing на witness host; використовувати `uname -r`, `modinfo -n/-F vermagic/-F firmware`, `dpkg-query`, `readelf -n`, `sha256sum` та Debian source/patch series. Якщо pairing не встановлено, не робити runtime inference. Не запускати повторну Vulkan enumeration/submit, probe attach, driver switch, MMIO, firmware чи reboot.
- **Лишаються UNPROVEN:** `+0x1e0` як RM handle, RM class/runlist/notifier/fence semantics, `BOOT0`, `0x137000A1`, кінцевий callback/producer поля `device+0xc06`, його зв'язок із BDF/RM `gpu_id`, повний userspace/package pairing, причина NVK↔NVIDIA gap та безпечний GP107 BAR0 register offset. Чотири channel-manager calls у self-test не закривають ці питання.
- **Розмежування стендів:** окремий Kali GP107 witness host має зафіксовані Nouveau boot, NVK enumeration і `TOP_GR_RUNLIST_0_OBSERVED`; конкретний user GR/compute channel → runlist та NONSTALL registration/ALLOW/refcount лишаються `UNPROVEN`. Ці факти не є доказом для H170. На GA-H170-Gaming 3 native Linux `wsm-hwcheck`, driver/firmware binding, Nouveau boot, Vulkan enumeration/channel/submit і functional tests залишаються **NOT RUN / NOT ASSESSED**.
- **Для всіх стендів:** physical BAR/MMIO, `resource0` contents read, driver unbind, RM/UVM ioctl, firmware/VBIOS mutation, BOOT0 register read, kernel instrumentation і reboot залишаються **NOT AUTHORIZED / NOT RUN**. Ledger лишається `deferred/read-safe-offset-unproven`; `owner-approval=not-inferred`; `physical-mmio=not-authorized`.
- GP107 [docs/20–21](https://github.com/juv4uk/gp107-nvidia-re/tree/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs) залишаються NVIDIA R580-only HOST_VISIBLE/HOST_COHERENT baseline та матрицею 108 точок на зовнішньому host, не NVK A/B і не H170 performance baseline. [docs/22](https://github.com/juv4uk/gp107-nvidia-re/blob/62a129608b57ca3d6cde1ca6d9beda0ba03130c5/docs/22-device-local-transfer-and-compute-phases.md) має оновлений code із memory dependencies та `memoryTypeBits`, але build, synchronization validation і фізичний rerun ще не прийняті; історичні DEVICE_LOCAL цифри — **EXPLORATORY / NOT ACCEPTED**.
- Для WSM це лише зовнішня GP107 software/source evidence. Вона не підвищує H170 `runtime_binding`, firmware presence, KMS/display, functional validation, package resolution або Free/Compatibility profile verdicts. Потрібен native Linux `wsm-hwcheck` report на самій GA-H170-Gaming 3 та точна звірка встановленого kernel/module/firmware closure.


## Runbook: native Linux звіт `wsm-hwcheck` для цієї машини

- Статус розділу: **процедура для власника; доказом стає лише отриманий файл звіту, а не цей текст**
- Власники контракту: [HWCHECK.md](HWCHECK.md) (що збирає колектор) і [REPORT-FORMAT.md](REPORT-FORMAT.md) (формат і семантика `unknown`)
- Мета: **один** прогін на фізичній машині дає **один** файл, з якого `scripts/draft_profile_evidence.py` будує `evidence.json` без другої перезагрузки в Linux
- Чого цей прогін не робить: не створює каталог профілю, не ставить жодного `pass`, не доводить, що графіка, мережа, звук або suspend працюють

### 1. Що мусить бути у файлі

Значення нижче — це поля звіту й те, що на цій платі має бути в них. Джерело істини — власний прогін; Windows/WSL-довідка вище не є доказом жодного з цих полів.

| Поле звіту | Очікування на GA-H170-Gaming 3 | Навіщо це потрібно профілю |
| --- | --- | --- |
| `schema_version` | `1.1.0` | `draft_profile_evidence.py` записує його в `report_schema_version` |
| `report_id` | `wsm-` + 24 hex-символи, випадковий на кожен прогін | `report_id` у bundle; без нього чернетка не створюється |
| `collected_at` | ISO-8601 UTC | з нього береться `verified_on` |
| `environment.architecture` | `x86_64` | перевірка, що звіт із цієї машини |
| `environment.kernel_release` | ядро live-середовища або встановленої системи | доказ анулюється, коли змінюється ядро |
| `environment.boot_mode` | `uefi` | профіль заявляється для UEFI |
| `environment.boot_mode_evidence` | непорожній рядок про `/sys/firmware/efi` | показує, на чому саме зроблено висновок |
| `environment.platform.board_name` | `GA-H170-Gaming 3-CF` (DMI `board_name`; `product_name` = `GA-H170-Gaming 3`) | ідентичність плати |
| `environment.platform.bios_version` / `bios_date` | те, що повернув DMI цього прогону | доказ анулюється, коли змінюється firmware |
| `devices[]` з `category: gpu` | **два** записи: `identity.vendor_id` `0x8086` / `device_id` `0x1912` (Intel HD 530) і `0x10de` / **`0x1c82`** (GTX 1050 Ti) | `hardware_signature.pci_ids` для матчера |
| `devices[]` GPU: `driver.status` | `bound` (є `bound_driver`), `none-known` (symlink драйвера відсутній) або `available-only` | головне питання сертифікації GPU |
| `devices[]` з `category: cpu` | `cpu.microcode`, `stepping`, `model_number`, `logical_processors` | доказ анулюється, коли змінюється мікрокод |
| `privacy.network_upload_performed` / `network_requests_performed` / `sensitive_identifiers_included` | `false` / `false` / `false` | звіт лишається локальним |

Ідентифікатори PCI колектор пише в sysfs-формі з префіксом (`"0x1c82"`), а підпис профілю — без нього (`10de:1c82`). Це не розбіжність: `wsm_install/profile_match.py` нормалізує обидві форми.

### 2. Перед завантаженням у Linux

На машині з мережею (Windows достатньо) підготувати дерево репозиторію на USB:

```sh
git clone --depth 1 https://github.com/juv4uk/wsm-desktop.git
```

Скопіювати теку `wsm-desktop` цілком на флешку. На самій H170 мережа не потрібна: колектор не робить жодного мережевого запиту (`privacy.network_requests_performed: false`, у `wsm_hwcheck/` немає мережевих викликів), і сторонніх залежностей часу виконання він не має. `jsonschema[format]` з `requirements-install.txt` потрібен лише для кроку перевірки схеми (п. 4, крок 5): на live ISO він уже в образі, на встановленій системі його треба мати заздалегідь, бо без мережі `pip install` не спрацює.

Підготувати на флешці порожню теку для звіту. Більше нічого не пишеться: збирач read-only і дисків не торкається.

### 3. Live ISO чи встановлена система

| | Live ISO | Встановлена система |
| --- | --- | --- |
| Що запускати | `wsm-hwcheck` з `/bin` — обгортка над `python3 -m wsm_hwcheck` (`systems/live-iso.scm`) | `python3 -m wsm_hwcheck` з кореня скопійованого дерева |
| Дерево репозиторію | уже в образі | з USB |
| `pci.ids` | найімовірніше відсутній: назви не з'являться, `vendor_id`/`device_id` лишаться | залежить від дистрибутива; перевірити `collectors[]` |
| `modules.alias` / `modules.dep` / `modules.builtin` | можуть бути відсутні або неповні (squashfs) → більше `unknown` | є `/lib/modules/$(uname -r)/` |
| Журнал ядра (`journalctl`/`dmesg`) | може бути недоступним без прав → `firmware.runtime_status: unknown` | те саме |
| Куди лягає звіт | `/tmp` — це RAM: **скопіювати на USB до перезавантаження** | будь-де на диску |
| `jsonschema[format]` для перевірки схеми | у образі | поставити заздалегідь |

Обидва варіанти дають native Linux звіт: контракт вимагає native Linux, а не встановлену систему. Live ISO достатньо для інвентаризації; встановлена система дає більше фактів (індекси модулів, журнал ядра). Обирається **один** прогін і **один** файл — змішувати два прогони не можна, у кожного свій `report_id`.

### 4. Порядок команд

З кореня дерева `wsm-desktop` (на live ISO — з будь-якого каталогу, бо `wsm-hwcheck` уже в `PATH`):

1. `cd wsm-desktop`
2. `python3 -m wsm_hwcheck --version` → мусить бути `wsm-hwcheck 0.3.0`. Інша версія означає, що дерево не з `main`; тоді звіт може не містити полів 1.1.0.
3. `python3 -m wsm_hwcheck --output ./hwcheck-report.json`
   (на live ISO: `wsm-hwcheck --output /tmp/wsm-hwcheck.json`)
   Код виходу 0 і непорожній файл. Без `--output` JSON друкується в stdout і у файл не потрапляє.
4. `python3 -m wsm_hwcheck.isa --report ./hwcheck-report.json > wsm-cpu-isa.json`
   Рівень `wsm-cpu-isa/1` для поля `isa_level` у bundle плюс крос-перевірка, що звіт справді з цієї машини (`cross_check.report_id`, попередження, якщо архітектура інша). Артефактом bundle цей файл бути не може: `artifacts[].kind` має закритий перелік `wsm-hwcheck-report` / `functional-test-log` (`schemas/profile-evidence.schema.json`). Зберігати його як робочий матеріал поруч зі звітом.
5. `python3 -m wsm_install --preflight --report ./hwcheck-report.json --backend guix --dry-run --classify`
   (на live ISO: `wsm-install --preflight --report /tmp/wsm-hwcheck.json --backend guix --dry-run --classify`)
   Код 0 — схема валідна. Код 2 — помилка схеми або читання файлу, звіт не годиться. Це той самий валідатор і той самий вибір схеми за оголошеною версією, що й у `scripts/draft_profile_evidence.py`, тому успіх тут означає, що чернетку bundle не заблокують на схемі.
   **Не читати вивід `--classify` як оцінку машини:** у свіжому звіті всі підсистеми будуть `unknown`, бо `functional_tests` порожній. Це нормально і не є помилкою схеми.
   Ця перевірка не вимагає extras `jsonschema[format]`; якщо пізніше `scripts/draft_profile_evidence.py` відмовить із «format validation is unavailable … install jsonschema[format]», це прогалина середовища (без extras перевірка `format` мовчки не виконується), а не дефект звіту: поставити `requirements-install.txt`, повторити перевірку схеми — звіт збирати заново не потрібно.
6. `sha256sum ./hwcheck-report.json` — записати результат.
7. Скопіювати `hwcheck-report.json` і `wsm-cpu-isa.json` на USB **до** виходу з Linux.

### 5. Що перевірити на машині, поки ще не вийшов з Linux

- `grep -n '"boot_mode"' ./hwcheck-report.json` → `"boot_mode": "uefi"` і змістовний `boot_mode_evidence`
- `grep -n '0x1c82' ./hwcheck-report.json` → рівно один запис GPU з `"vendor_id": "0x10de"` і `"device_id": "0x1c82"`
- `grep -n '"category": "gpu"' ./hwcheck-report.json` → два записи GPU (Intel `0x1912` і NVIDIA `0x1c82`)
- `grep -n '"board_name"' ./hwcheck-report.json` → `GA-H170-Gaming 3-CF`
- `grep -n 'wsm-pci-ids-database' -A2 ./hwcheck-report.json` → `"available": true` або `false` (див. п. 6, обидва прийнятні)
- `grep -n '"warnings"' -A8 ./hwcheck-report.json` → прочитати кожен рядок і зрозуміти, чому він там
- крок 5 з п. 4 завершився з кодом 0
- `sha256sum` записано, файл на USB відкривається і його розмір не 0

Якщо хоч один пункт не сходиться — це та сама перезагрузка в Linux, яку дешевше повторити зараз, ніж після повернення у Windows.

### 6. `unknown`: коли це прийнятно, а коли прогін треба повторити

`unknown` — це штатна відповідь, а не поломка: контракт прямо забороняє перетворювати відсутнє джерело на відмову. Але є факти, без яких профіль не створити.

**Прийнятно, повторювати не треба:**

| Що видно у звіті | Чому це нормально |
| --- | --- |
| `wsm-pci-ids-database: available false` + warning про назви | немає локального `pci.ids`: `vendor_id`/`device_id` лишаються, назви моделей відсутні. Матчер профілю працює на парах `vendor:device`, не на назвах |
| `firmware.runtime_status: unknown` у GPU/NIC | ядро не повідомило про firmware саме цього пристрою, або журнал ядра недоступний. Наявність blob'а звіт не вигадує |
| `gpu.drm_cards` у `unavailable` | для цієї PCI-функції немає DRM-вузла (напр. драйвер не прив'язаний). `boot_vga` при цьому все одно записаний |
| `gpu.pci_link.max_speed` / `max_width` у `unavailable` | sysfs не віддав максимальні значення; поточні записані |
| `cpu.microcode` у `unavailable` | ні `/proc/cpuinfo`, ні `/sys/.../microcode/version` не дали ревізії |
| `network.interfaces: []` | драйвер не прив'язаний, тому немає інтерфейсу, чий sysfs-зв'язок веде до цієї функції |
| `storage.transport` у `unavailable` | предки block-пристрою в sysfs не дали шину |
| `identity.revision: "x.x"` у платі | це DMI-заглушка Gigabyte; ревізія плати лишається `unknown`, як і записано у статусі цього документа |
| `environment.virtualization: "unknown"` | на bare metal це нормально: колектор називає гіпервізор лише тоді, коли має доказ, а `none-detected` не вигадує |
| `wsm-current-boot-kernel-log: available false` | журнал закритий правами або недоступний; наслідок — `firmware.runtime_status: unknown`, що прийнятно |

**Прогін треба повторити, якщо:**

| Ознака | Що це означає |
| --- | --- |
| `environment.boot_mode: "unknown"` | немає ні `/sys/firmware/efi`, ні x86 DMI — це не та машина й не те середовище (контейнер, обмежена оболонка, чужий root) |
| `environment.virtualization` = `kvm` / `qemu` / `vmware` / `hyper-v` / `xen` | звіт знято у віртуальній машині; для профілю фізичної H170 він непридатний |
| немає запису GPU з `0x1c82` | карта вимкнена у firmware, в іншому слоті або не ініціалізувалась; без цієї пари `hardware_signature` не скласти |
| `devices` порожній або без `cpu`/`motherboard` | читання sysfs/procfs не відбулося |
| `board_name` відсутній або не `GA-H170-Gaming 3…` | звіт з іншої машини |
| перевірка схеми (п. 4, крок 5) повернула 2 | файл обрізаний або змінений; зібрати заново |
| `report_id` або `collected_at` відсутні | звіт не від цього колектора |
| `python3 -m wsm_hwcheck --version` не `0.3.0` | дерево не з `main`; полів 1.1.0 може не бути |
| файл редагували, переформатували або перезберегли після збору | SHA-256 у bundle рахується з точних байтів; такий файл уже не той, що зібрано |

Повторний прогін створює **новий** `report_id`. Bundle прив'язується до одного звіту, тому не можна взяти `report_id` з першого прогону, а факти — з другого.

### 7. Чого звіт не може містити і чому

- **Firmware blob'ів, які ядро не повідомило.** Звіт фіксує `firmware.runtime_status` і `kernel_log_evidence`, а не вміст blob'ів. Для цієї плати це принципово: GP107 GR FECS/GPCCS, i915 DMC і Intel CPU microcode — невільні компоненти, і WSM не включає й не перерозповсюджує їх (див. [матрицю firmware](H170-FIRMWARE-MATRIX.md)). Відсутність рядка в журналі дає `unknown`, а не `missing`: «не спостерігали» і «немає» — різні твердження.
- **MAC-адрес, серійних номерів, UUID, імені хоста, імені користувача, IP-адрес, WWN.** Їх виключає профіль приватності strict-local; `privacy.redactions_applied` перелічує категорії. Тому в записі мережі є PCI-ідентичність і назви інтерфейсів, але немає `address`.
- **Таблиці розділів, типів файлових систем і записів завантажувача.** Колектор обіцяє не торкатися блокових пристроїв, тому ці факти збираються іншими засобами й іншими доказами.
- **Ідентичності монітора з EDID і зв'язку «конектор → GPU».** Це окрема робота (#18); запис `display` містить стан конектора й заявлені режими, і це не доказ, що режим проходить через фактичний шлях GPU → конектор → кабель → монітор.
- **Результатів функціональних тестів.** `functional_tests` лишається `[]`; інвентаризація не доводить, що HDMI, звук, мережа або suspend працюють. Саме тому bundle вимагає окремих `functional-test-log` артефактів.
- **Рівня ISA.** Він навмисно не дублюється у звіті, а живе в окремому контракті `wsm-cpu-isa/1` — тому крок 4 у п. 4 обов'язковий.

### 8. Що передати назад

1. Точні байти `hwcheck-report.json` — не перезберігати, не форматувати, не «виправити» жодне поле: SHA-256 цього файлу входить у bundle.
2. `sha256sum` цього файлу.
3. `report_id`, `schema_version`, `collected_at`, `environment.kernel_release`.
4. Вивід `wsm-cpu-isa.json`.
5. Текст виводу перевірки схеми (крок 5) з кодом виходу.
6. Перелік `collectors[]` зі `available: false` і всі рядки `warnings`, які були на екрані.
7. Одне речення: live ISO чи встановлена система, і версія `wsm-hwcheck`.

### 9. Що робиться далі — не в цьому прогоні

Каталог `profiles/hardware/gigabyte/ga-h170-gaming3/` цим runbook не створюється: спершу звіт, потім каталог із `profile.scm` на основі `profiles/hardware/template.scm`, потім `scripts/draft_profile_evidence.py`, потім окремі функціональні тести з логами в `artifacts/` і `scripts/check_profile_evidence.py`. Порядок і команди — [AGENTS.md](../../AGENTS.md), розділ 3; контракт — [HARDWARE-PROFILE-EVIDENCE.md](../HARDWARE-PROFILE-EVIDENCE.md).

Один прогін достатній для чернетки: генератор читає зі звіту рівно `report_id`, `schema_version`, `collected_at`, `devices[].category`, пари PCI з `identity`, `discovery_status`, `firmware.runtime_status`, `functional_tests` і `warnings`. Усі ці поля збираються за один запуск, тому другої перезагрузки в Linux для `evidence.json` не потрібно — потрібні лише функціональні тести, які виконуються в тому ж завантаженні або пізніше.
