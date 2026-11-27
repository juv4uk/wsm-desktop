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

- [Матриця можливостей](https://github.com/juv4uk/gp107-nvidia-re/blob/master/docs/05-gp107-capability-matrix.md)
  розділяє runtime-proven, statically proven, interpretation та UNPROVEN.
  Вона не стверджує, що RM probes відкрили BAR0/MMIO або довели повний
  GPU command submission.
- [NVK compute result](https://github.com/juv4uk/gp107-nvidia-re/blob/master/docs/14-nvk-vector-add-compute-result.md)
  фіксує фізичний vector-add compute PASS на GP107. Це доводить виконання
  конкретного Vulkan compute workload, а не daily-driver completeness.
- [Порівняння NVK/NVIDIA](https://github.com/juv4uk/gp107-nvidia-re/blob/master/docs/17-vulkan-compute-benchmark-open-vs-proprietary.md)
  має три повтори обох стеків, але було зняте до виправлень benchmark
  harness. [Документ надійності](https://github.com/juv4uk/gp107-nvidia-re/blob/master/docs/18-procedural-deviation-and-benchmark-reliability.md)
  прямо позначає ці цифри як історичні, не як поточний acceptance baseline.
- [Надійна NVIDIA baseline](https://github.com/juv4uk/gp107-nvidia-re/blob/master/docs/20-reliability-baseline-proprietary.md)
  дає median-of-three: 20,310 ns / 2.4201 GB/s для 4,096 елементів;
  1,267,551 ns / 9.9269 GB/s для 1 Mi; 10,616,000 ns / 9.4822 GB/s
  для 8 Mi. Це proprietary ICD 580.196.11 і HOST_VISIBLE|HOST_COHERENT
  шлях, а не VRAM bandwidth.
- [Матриця workgroup × batching](https://github.com/juv4uk/gp107-nvidia-re/blob/master/docs/21-proprietary-performance-matrix.md)
  містить 108 успішних NVIDIA runtime points. Вона вказує на помітний
  submit overhead для малих задач і workload-залежний вплив local size.
- [DEVICE_LOCAL transfer/compute](https://github.com/juv4uk/gp107-nvidia-re/blob/master/docs/22-device-local-transfer-and-compute-phases.md)
  має 12 exploratory points і корисні raw logs, але локальне рев'ю
  GP107 issue #28 виявило відсутні Vulkan memory dependencies між H2D →
  compute → D2H, неперевірений `memoryTypeBits` та відсутність GPU
  timestamp queries. Тому docs/22 зараз **EXPLORATORY / NOT ACCEPTED**;
  його 90.46 GB/s і 52.39 ms не використовувати як валідні висновки.
  Потрібні barriers, synchronization validation, memoryTypeBits checks
  та повторний запуск із новими артефактами.

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
3. Найближча оптимізаційна гіпотеза — мінімізувати зайві submit/fence
   цикли та тримати повторно використовувані дані у DEVICE_LOCAL пам'яті.
   Проте docs/22 поки не має коректних memory dependencies і не приймається;
   спочатку виправити synchronization та measurement methodology, потім
   повторити proprietary baseline і лише після цього порівнювати з NVK.
4. Не обіцяти універсальне перевершення NVIDIA. Спершу визначити workload,
   де WSM має виміряну перевагу; окремо документувати обмеження reclocking,
   power/clock control та відсутні функції.


## Пов'язана матриця firmware та microcode

Для зведеного огляду firmware, microcode, ліцензій і функціональних обмежень
див. [H170 firmware/capability matrix](H170-FIRMWARE-MATRIX.md).

## Актуалізація GP107: software hardening і межа апаратних доказів (2026-11-28)

Канонічний знімок зовнішнього дослідницького репозиторію:
[juv4uk/gp107-nvidia-re @ 8cb70ae489474eccbec9ce7809f642a11eefc8c1](https://github.com/juv4uk/gp107-nvidia-re/tree/8cb70ae489474eccbec9ce7809f642a11eefc8c1).
Це пізніший source snapshot для GP107 research, а не доказ на H170.

- [docs/29](https://github.com/juv4uk/gp107-nvidia-re/blob/8cb70ae489474eccbec9ce7809f642a11eefc8c1/docs/29-userspace-capability-driver.md)
  і [docs/30](https://github.com/juv4uk/gp107-nvidia-re/blob/8cb70ae489474eccbec9ce7809f642a11eefc8c1/docs/30-userspace-capability-ledger.md)
  описують C11 userspace/sysfs identity, fail-closed driver binding та capability ledger.
  Після merged hardening приватний mapper використовує pinned PCI directory fd:
  перевіряє BDF, vendor/device/revision, subsystem IDs, `uevent` і PCI config
  через цей самий fd; `resource0` відкривається відносно нього з
  `O_NOFOLLOW`, розмір перевіряється через `fstat`, а driver binding
  повторно перевіряється перед read-only mapping. Synthetic substitution
  witnesses доводять відмову на підміні BDF/device у fixture, а не на фізичній H170.
- Це **не** означає, що фізичний BAR0 read став безпечним або був виконаний.
  У поточному GP107 `master` лишається production path до
  `openat(resource0)` / `mmap(PROT_READ)`; сам `PROT_READ` не доводить,
  що читання довільного регістру не має side effects. Фізичний MMIO/BAR,
  driver unbind і BOOT0 залишаються **NOT AUTHORIZED / NOT RUN / UNPROVEN**.
- [GP107 PR #53](https://github.com/juv4uk/gp107-nvidia-re/pull/53) пропонує
  наступний безпечніший крок: після identity/driver/BAR/offset software gates
  повертати `read-safe-offset-unproven`, не відкривати `resource0` і не
  виконувати mapping/read. На момент цього знімка PR **не злитий**:
  exact-head run `46084831447` завершився failure у необов'язковому host
  inventory tail; review також вимагає перенести новий pinned-dirfd захист із
  master у PR перед повторним CI. Тому це pending candidate, не чинний
  merged contract і не підстава запускати MMIO.
- GP107 [docs/20–21](https://github.com/juv4uk/gp107-nvidia-re/tree/8cb70ae489474eccbec9ce7809f642a11eefc8c1/docs)
  лишаються NVIDIA R580-only HOST_VISIBLE/HOST_COHERENT baseline та матрицею
  108 точок на окремому тестовому host. Це не NVK A/B і не H170 performance
  baseline. [docs/22](https://github.com/juv4uk/gp107-nvidia-re/blob/8cb70ae489474eccbec9ce7809f642a11eefc8c1/docs/22-device-local-transfer-and-compute-phases.md)
  містить виправлений command-stream код із memory dependencies та
  `memoryTypeBits` check, але виправлення ще потребує build, synchronization
  validation і нових фізичних повторів; історичні DEVICE_LOCAL цифри лишаються
  **NOT ACCEPTED / EXPLORATORY**.
- Для WSM це лише зовнішня device-level/software evidence. Вона не підвищує
  H170 `runtime_binding`, firmware presence, KMS/display, functional validation
  або Free/Compatibility profile verdicts. Їхні стани лишаються такими, як
  підтверджено власними H170 manifests; потрібен окремий native Linux
  `wsm-hwcheck` report на самій платі.
