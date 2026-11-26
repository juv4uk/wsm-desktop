# Швидкість: що беремо з Clear Linux, а що ні

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **частково реалізовано** (`wsm/systems/performance.scm`), не виміряно
- Задача: [#151](https://github.com/juv4uk/wsm-desktop/issues/151), батьківська [#147](https://github.com/juv4uk/wsm-desktop/issues/147)
- План поточного виправлення provenance: [virtualization evidence](superpowers/plans/2026-11-26-perf-virtualization-evidence.md)
- План пасивних вимірів: [PSI та zram observations](superpowers/plans/2026-11-26-perf-pressure-observations.md)
- План Guix-native повторного використання артефактів: [підписані derivations і substitutes](superpowers/plans/2026-11-26-guix-native-artifact-reuse.md)
- План boot-мірок: [read-only boot profile collector](superpowers/plans/2026-11-26-boot-profile-collector.md)
- Рішення: [ADR 0007](decisions/0007-clear-linux-principles.md)

## Головна різниця, яку варто зрозуміти

Clear Linux був швидким тому, що **перебудовував увесь світ** власним конвеєром
компіляторів: PGO, LTO, BOLT, агресивні прапорці, власні патчі. Це працює, коли в
тебе є Intel, build farm і команда компіляторів. У WSM немає ні першого, ні
другого, ні третього.

Копіювати `-O3 -march=native` для всієї системи означає зробити збірку
невідтворюваною й отримати дистрибутив, який падає на іншому залізі. Це прямо
суперечить принципу 4 проєкту.

## Що беремо: `--tune`

У Guix є чесніший механізм, ніж глобальні прапорці — **`--tune`**. Він оптимізує
лише пакети, позначені властивістю `tunable?`, збирає їх із `-march=<cpu>`,
**графтить** у граф залежностей (тож залежні не перебудовуються) і записує
перетворення так, що збірку можна повторити.

Ключове: він не жертвує відтворюваністю. З погляду Guix це просто інший, але
чітко визначений граф залежностей.

```sh
guix package --tune=x86-64-v3 -i blender
guix shell --tune eigen-benchmarks -- benchBlasGemm 240 240 240
```

Ціна, яку варто знати: для налаштованих пакетів **не запускаються тести** — build
farm може не мати цієї мікроархітектури. Тобто `--tune` — це опція для
користувача, а не для релізного образу.

Тому в WSM:

- **базовий образ збирається без `--tune`** — переносимість і тести важливіші;
- користувач, який хоче швидше на своєму залізі, ставить `--tune` сам, свідомо;
- рівень, який підтримує машина, визначається контрактом `wsm-cpu-isa/1`
  ([CPU-ISA-EVIDENCE.md](hardware/CPU-ISA-EVIDENCE.md)), а не вгадується.

## Що беремо: три служби замість обіцянок

`wsm/systems/performance.scm` підключається до `desktop.scm` і додає:

| Служба | Що зменшує | Чому саме вона |
| --- | --- | --- |
| `zram-device-service-type` (zstd, 4G) | затримку при нестачі пам'яті | без zram ядро витісняє сторінки на диск, і затримка зростає в десятки разів |
| `earlyoom-service-type` | час повного зависання | штатний OOM killer прокидається запізно; earlyoom прибирає найбільшого споживача раніше |
| `fstrim-service-type` | деградацію запису на SSD | не прискорює, але без нього швидкість запису падає з часом |

Це не «прискорювач». Кожна служба прибирає конкретну затримку, яку користувач
відчуває щодня, і кожну можна виміряти окремо.

## Що свідомо не беремо

- **Глобальні `-O3` / `-march=native`** — невідтворюваність і падіння на іншому залізі.
- **PGO для всієї системи** — ламає відтворюваність, якщо профіль не зафіксований; для окремих пакетів — можливо, але це рішення пакувальника, а не дистрибутива.
- **`mitigations=off`** — це не «швидше», це «безпека вимкнена». Такого прапорця в профілях не буде.
- **`swupd`, bundles, autospec** — другий пакетний менеджер (ADR 0004).
- **Твердження «найшвидший»** — без вимірювань це маркетинг. Clear Linux міг собі це дозволити, маючи Phoronix-бенчмарки щотижня; WSM не має.

## Як це міряти: harness

`scripts/measure_baseline.py` виконує п'ять низькошумних навантажень і пише
версійований артефакт `wsm-perf-baseline/1`:

```sh
python3 scripts/measure_baseline.py --mode physical --output baseline.json
python3 scripts/measure_baseline.py --mode qemu --output qemu-baseline.json
```

`--mode` задає очікуваний режим; це не override detector-а. Для QEMU-гостя
запис `comparison_eligible` можливий лише після позитивного read-only evidence.
Для фізичного host поточний collector може повернути лише `unknown`, якщо не
має достатнього джерела bare-metal evidence — не підміняйте це припущенням.

Що зафіксовано в артефакті, окрім чисел:

- **запитаний режим** (`mode`) — лише заява оператора, а не доказ середовища;
- **виявлена віртуалізація** (`detected_virtualization`) і
  `virtualization_source` — значення з read-only
  `wsm_hwcheck.collector.collect_report()`, джерело
  `wsm-hwcheck-sysfs/0.2.0`;
- **узгодженість режиму** (`mode_evidence`): `consistent`, `mismatch` або
  `unknown`. `physical` з будь-яким позитивним VM evidence — `mismatch`;
  відсутність hypervisor marker — лише `unknown`, не доказ bare metal.
  `qemu` приймає виявлені `qemu` або `kvm`; VMware, Hyper-V, Xen та інші
  VM-платформи не зараховуються як QEMU;
- **придатність до порівняння** (`comparison_eligible`) — `true` лише за
  `mode_evidence=consistent`. Для порівнянь додатково мають збігатися точний
  `detected_virtualization`, ISA та інші умови. Значення `qemu` і `kvm`
  зберігаються окремо: ця перевірка не доводить режим TCG/KVM acceleration;
- ядро, машина, версія Python, модель CPU, **рівень ISA** (з контракту
  `wsm-cpu-isa/1`), пам'ять, governor;
- клас сховища — свідомо `unknown`: угадувати «ssd» з імені пристрою було б
  вигадкою;
- кількість повторів, медіана, p90, MAD і відносний розкид. Метод і номер
  порядкового спостереження збережено як `p90_method=nearest-rank` та
  `p90_rank`; p90 — це `ceil(0.90 × n)`-те значення у відсортованій вибірці,
  без інтерполяції. За типової кількості п'ять повторів p90 закономірно є
  п'ятим значенням (максимумом цієї малої вибірки), а не оцінкою 90-го
  перцентиля генерального розподілу.

Артефакти, створені до tool version `0.2.0`, не містять virtualization
evidence і не можуть вважатися придатними для підтвердженого порівняння режимів.
Наразі collector не доводить bare-metal лише за відсутністю ознак гіпервізора;
тому запит `--mode physical` без окремого позитивного джерела залишається
`unknown` і `comparison_eligible=false`. Benchmark усе одно записує сирі
вимірювання, але не підвищує їх до підтвердженого фізичного baseline.

### Read-only pressure observations

Producer tool version `0.3.0` додає до кожного workload результат
`system_pressure`. Після warm-up і безпосередньо перед/після п'яти чи більше
виміряних повторів harness зчитує:

- **PSI** з `/proc/pressure/{cpu,memory,io}`: наявні рядки `some/full`,
  середні `avg10/avg60/avg300` та дельту cumulative `total` у мікросекундах.
  Рядок `full` може бути відсутнім у деяких kernel versions; parser не вимагає
  його для `cpu`. Семантика та одиниці описані в
  [Linux PSI documentation](https://docs.kernel.org/accounting/psi.html).
- **zram** з `/sys/block/zramX`: активний compressor і лише стан backing
  device (`none`, `configured` або `unknown`; шлях `/dev/...` не записується),
  `mm_stat` як сирі before/after поля (байтові розміри та page counters без
  спільної дельти), `io_stat` як лічильники подій, а `bd_stat` як лічильники
  обсягів у блоках по 4 KiB з дельтою. Поля відповідають
  [офіційній документації Linux zram](https://docs.kernel.org/admin-guide/blockdev/zram.html).
  Старіша версія ядра з неповним `mm_stat`, відсутній пристрій або reset
  counters лишають доказ `partial/unknown`, не перетворюються на нуль.

PSI й zram — **system-wide** джерела: вони включають активність інших процесів
і описують інтервал workload, але не доводять причинний зв'язок із конкретним
процесом. Їх використовуємо як контекст і для виявлення корельованого pressure,
не як regression threshold та не як автоматичний діагноз. Для інтерпретації
абсолютних дельт кожен workload також записує `sample_window_seconds` —
тривалість серії виміряних повторів. Читання telemetry відбувається поза timed
region, не змінює самі workload timings і не пише до procfs/sysfs. Це
виконується лише під час явного запуску benchmark, ніколи в hardware preflight.

Артефакти tool version `0.2.0` мають virtualization provenance, але ще не
містять `system_pressure`; відсутність цих полів у старому результаті означає
`unknown`, а не нульовий тиск. zswap лишається окремим opt-in експериментом:
він обмінює CPU cycles на можливе зменшення swap I/O, а не є автоматично
кращою заміною zram ([Linux zswap documentation](https://www.kernel.org/doc/html/latest/admin-guide/mm/zswap.html)).
Жодних змін compressor, розміру zram, swappiness, zswap, governor чи power
limits ця telemetry не виконує.

**Шум визначається, а не приховується.** Прогін вважається шумним, якщо MAD або
відхилення p90 перевищує 5% медіани. MAD сам по собі не ловить одинака серед
однакових значень, тому перевіряються обидві міри.

Перший живий прогін у середовищі розробки це й показав: три навантаження чисті,
два — ні, і артефакт прямо це сказав замість того, щоб видати середнє.

### Правило, яке з'явилося після першого прогону

Навантаження, яке триває кілька мілісекунд, міряє таймер, а не машину. Перша
версія мала 8 MiB для пам'яті й 4 MiB для запису — і дала розкид 716% та 27%
відповідно. Усі навантаження відкалібровано так, щоб тривати десяті секунди.

### Boot milestones та critical path systemd

`scripts/collect_boot_profile.py` — окрема ручна команда для одного поточного
boot. Вона не входить до hardware preflight, installer, звичайного CI або
`measure_baseline.py`:

```sh
python3 scripts/collect_boot_profile.py --output boot-profile.json
```

Колектор викликає лише фіксований read-only набір `systemd-analyze` команд:
`--version`, `time`, `blame`, `critical-chain` для default target та
`critical-chain graphical.target`. Кожний результат зберігає argv, stdout,
stderr, exit code, тривалість та окремі ознаки timeout/truncation. Командний
у JSON-артефакті зберігається не більше 64 KiB stdout і stderr на команду;
timeout кожного виклику за
замовчуванням 10 секунд і не може перевищувати 60 секунд. Немає shell або
довільних unit names з аргументів користувача.

Артефакт `wsm-boot-profile/1` містить kernel/machine, virtualization evidence,
uptime та короткий digest boot ID замість сирого UUID. Відсутній
`systemd-analyze`, неактивний system manager, nonzero exit, malformed procfs
або timeout залишаються `unavailable/partial/unknown`, не нулем і не pass.
Один артефакт — це одне спостереження конкретного boot; незалежні samples
збираються між окремими boot-ами, не повторними запусками цієї команди в одній
сесії.

**Обмеження інтерпретації є частиною контракту:**

- `systemd-analyze time` показує kernel/initrd/userspace до моменту, коли
  сервіси були spawned. Це не доводить, що всі вони завершили ініціалізацію,
  desktop готовий або диск idle.
- `blame` вимірює час у стані `activating`, не показує `Type=simple` та
  execution-queue wait, не включає units на кшталт device units без
  `activating` і не враховує паралельне виконання. Високий рядок не означає
  автоматично найбільшу затримку для користувача.
- `critical-chain` показує один time-critical dependency path, але не всі
  паралельні роботи. Socket activation, device units, jobs і timeouts мають
  окремі caveats upstream.
- Firmware/loader час може з'являтися у `systemd-analyze time`, якщо UEFI
  bootloader експортує `LoaderTime*` через EFI Boot Loader Interface. Якщо
  значень немає, це `unknown`, а не нуль; наш колектор не читає і не змінює
  EFI variables напряму. Для повного виміру cold desktop readiness все одно
  потрібен окремий session-level marker.

Колектор лише читає поточний стан. Він не змінює units, targets, bootloader,
EFI variables, диски, governor або power controls. Перегляд і порівняння
профілів мають зберігати окремі physical/QEMU класи та однакові умови.
Див. [systemd-analyze upstream documentation](https://www.freedesktop.org/software/systemd/man/latest/systemd-analyze.html).

## Як це міряти далі

Задача [#151](https://github.com/juv4uk/wsm-desktop/issues/151) лишається відкритою: потрібен baseline boot, service startup і типовий workload, знятий на реальному залізі, з однаковими умовами. Доти будь-яке твердження про швидкість — не твердження.

Порівнювати з Clear Linux **неможливо**: він не оновлюється з липня 2025, тож його числа не відтворювані на поточних ядрах. Порівнювати треба з поточними дистрибутивами.
