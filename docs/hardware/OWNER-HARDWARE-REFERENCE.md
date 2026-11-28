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
- [DEVICE_LOCAL transfer/compute](https://github.com/juv4uk/gp107-nvidia-re/blob/8255da482af3c404147b5eefcb0ba0caaa43984a/docs/22-device-local-transfer-and-compute-phases.md)
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

## Актуалізація GP107: provenance, UVM caller chain і Nouveau firmware (2026-11-28)

Канонічний зовнішній GP107 research snapshot:
[juv4uk/gp107-nvidia-re @ `f5f2cd3fc494cc072f5b10645260e36241bd1f98`](https://github.com/juv4uk/gp107-nvidia-re/tree/f5f2cd3fc494cc072f5b10645260e36241bd1f98).
Це зовнішнє дослідження окремих стендів з GPU `10de:1c82`, а не доказ роботи
плати GA-H170-Gaming 3 з Guix.

- **C/Pascal identity та MMIO gate:** merged GP107 #52/#54/#55/#56 залишили PCI identity перевірку через pinned dirfd, а публічний C/Pascal read API завершується `SAFE_OFFSET_UNPROVEN=21` до відкриття вмісту `resource0`, BAR mapping або register read. Pascal має п'ять synthetic substitution/binding fixtures; exact static/FPC 3.2.2 CI для #56 пройшов (`46087161680`). Це software/fixture evidence, не physical MMIO і не H170 acceptance.
- **R580 package pairing — окремий Kali test host:** [docs/36](https://github.com/juv4uk/gp107-nvidia-re/blob/f5f2cd3fc494cc072f5b10645260e36241bd1f98/docs/36-r580-artifact-pairing.md) зіставляє встановлені `nvidia.ko.xz`/`nvidia-uvm.ko.xz`, DKMS outputs, REA targets і завантажені proprietary modules за package/version `580.196.11`, `srcversion`, SHA-256 та GNU Build ID. Це закриває identity саме на тому Kali host; не доводить, що на H170 встановлена така сама версія або kernel ABI, і не є pairing для Nouveau.
- **UVM/BTF та прямі caller-и:** [docs/34–35](https://github.com/juv4uk/gp107-nvidia-re/tree/f5f2cd3fc494cc072f5b10645260e36241bd1f98/docs) доводять BTF-ланцюг `parent_gpus → uvm_parent_gpu_t → gpus → uvm_gpu_t → channel_manager`. [docs/37](https://github.com/juv4uk/gp107-nvidia-re/blob/f5f2cd3fc494cc072f5b10645260e36241bd1f98/docs/37-rea-p1-add-gpu-call-sites.md) знаходить рівно два прямі call-site `add_gpu` у дизасембльованих code sections: `0x0801eb42` і `0x0801ebf7`, обидва в `uvm_gpu_retain_by_uuid`. [docs/38](https://github.com/juv4uk/gp107-nvidia-re/blob/f5f2cd3fc494cc072f5b10645260e36241bd1f98/docs/38-rea-p1-register-gpu-uuid-chain.md) доводить статичний ланцюг `uvm_api_register_gpu → uvm_va_space_register_gpu → uvm_gpu_retain_by_uuid → add_gpu`; UUID приходить із першого поля ioctl-параметра. Userspace producer цього поля та відповідність UUID до PCI BDF/RM `gpu_id` лишаються `UNPROVEN`. Повний прототип `add_gpu`, непрямі call paths і RM class/channel/fence semantics теж не слід виводити з цих прямих викликів.
- **Nouveau firmware map:** [docs/39](https://github.com/juv4uk/gp107-nvidia-re/blob/f5f2cd3fc494cc072f5b10645260e36241bd1f98/docs/39-gp107-nouveau-firmware-dependency-map.md) — source-only карта, pinned до Linux source `f4585067150b85e33f60876149a6e742928da75e` і NVIDIA/linux-firmware WHENCE snapshot. Вона перелічує GP107 GR FECS/GPCCS та software-context файли, спільні GP102 ACR paths, SEC2 v0/v1 candidates і NVDEC scrubber. Це `SOURCE_CONFIRMED`/`SOURCE_CANDIDATE`, а не доказ конкретного boot request/load, package presence у Guix closure/initrd/ISO чи runtime pairing із завантаженим `nouveau.ko`.
- **Ліцензійна межа:** WHENCE посилається на `LICENCE.nvidia`; її Open Source Exception має умови щодо OSI-approved OS license, незмінених binary files і доставки копії ліцензії. Це не юридичне підтвердження можливості розповсюдження в WSM: #367 щодо ефективної `LicenseRef-Volnist` залишається невирішеним. Не копіювати blobs до Free, Compatibility, channel або ISO; Compatibility лишається лише кандидатом до окремого правового та package/closure review.
- **Що не змінило статус:** безпечний GP107 BAR0 offset, BOOT0, RM handle/class/runlist/notifier/fence, BDF ↔ RM `gpu_id`, причина NVK↔NVIDIA compute gap — `UNPROVEN`. Фізичний MMIO/BAR, `resource0` read, driver unbind, RM/UVM ioctl, firmware/VBIOS, GPU submit та reboot лишаються **NOT AUTHORIZED / NOT RUN**.

Для WSM це зовнішні software/source та окремо-host evidence. Вони не підвищують
H170 `runtime_binding`, firmware presence, KMS/display, functional validation,
package resolution чи Free/Compatibility verdicts. Потрібен native Linux
`wsm-hwcheck` report на самій GA-H170-Gaming 3 та точна звірка її kernel,
driver і firmware closure.
