# WSM Desktop 0.1.0-rc3 — Minimal Live Installer Preview

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Це компактний live-носій на основі `systems/live-minimal.scm`: без KDE/Qt,
із мережею, апаратним preflight та власним WSM CLI/TUI. Він призначений для
завантаження WSM на слабкому обладнанні, збору локального звіту про пристрої
та відкриття майстра планування інсталяції.

> **Статус доказів:** цей документ описує поточний source-профіль у репозиторії. Він сам по собі не доводить, що раніше опублікований ISO містить ці самі зміни.
> Для конкретного ISO звіряйте `source_commit` у `release-manifest.json`, checksum образу та artifact-specific evidence у [реєстрі перевірених артефактів](VERIFIED-ARTIFACTS.md). Якщо manifest/evidence для конкретного артефакту відсутній, його відповідність поточному source лишається `unknown`.

## Запуск

1. Запишіть ISO на USB або відкрийте його у віртуальній машині.
2. Перейдіть на консоль `tty2` (`Ctrl+Alt+F2`): там налаштовано автоматичний
   вхід користувача `wsm`. `tty1` і serial console лишаються для boot logs.
3. Запустіть `wsm-install-live`.

Команда створює апаратний звіт у приватному тимчасовому каталозі, запускає
WSM TUI та після завершення видаляє тимчасові дані. Також доступні
`wsm-hwcheck --help` і `wsm-install --help`.

## Мова та клавіатура

- Українська — основна локаль live-консолі; для введення шляхів і паролів
  доступна англійська розкладка US.
- Перемикання US/UA — `Alt+Shift`.
- У TUI працюють стрілки або `j/k`; на українській розкладці — також `о/л`.
  Вихід — `q` або `й`.
- Для кирилиці й рамок TUI на `tty2` налаштовано консольний шрифт
  `LatGrkCyr-8x16`.

## Рівні перевірки

Не змішуйте три різні результати:

- **Source/unit checks** перевіряють декларацію профілю, повідомлення та
  нормалізацію клавіш. Вони не запускають Guix і не доводять, що tty реально
  відображає кирилицю.
- **BIOS/UEFI marker smoke** через `scripts/qemu_boot_smoke.py` перевіряє,
  що ISO доходить до `WSM_LIVE_READY`. Він не перевіряє інтерактивне
  перемикання розкладки, шрифт чи TUI.
- **`make qemu-acceptance-manual`** запускає generic Linux guest,
  hwcheck/install preflight і CXL acceptance. Він не завантажує
  `systems/live-minimal.scm` як ISO й не є доказом роботи цього TTY user journey.

### Інтерактивний TTY smoke у QEMU

Виконуйте його на ISO, зібраному з точного source commit, який перевіряєте.
Створіть приватний тимчасовий каталог. VM має бути на TCG, без мережі,
host passthrough і віртуального жорсткого диска; єдиний block device — ISO
як CD-ROM:

```sh
RUN_DIR="$(mktemp -d)"
chmod 700 "$RUN_DIR"
WSM_ISO_DIR="$RUN_DIR/build" WSM_LIVE_PROFILE=systems/live-minimal.scm make image-live-minimal
ISO="$RUN_DIR/build/wsm-desktop-live.iso"
test -L "$ISO" && test -s "$ISO"
```

BIOS-запуск:

```sh
qemu-system-x86_64 \
  -machine q35,accel=tcg -m 2048 -smp 2 \
  -cdrom "$ISO" -boot order=d -nic none -display gtk \
  -serial "file:$RUN_DIR/bios-serial.log" -no-reboot
```

UEFI-запуск використовує read-only OVMF Code та окрему тимчасову копію VARS.
Не підключайте постійне NVRAM сховище хоста:

```sh
OVMF_CODE=/usr/share/OVMF/OVMF_CODE_4M.fd
OVMF_VARS_TEMPLATE=/usr/share/OVMF/OVMF_VARS_4M.fd
cp "$OVMF_VARS_TEMPLATE" "$RUN_DIR/OVMF_VARS.fd"
qemu-system-x86_64 \
  -machine q35,accel=tcg -m 2048 -smp 2 \
  -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE" \
  -drive if=pflash,format=raw,file="$RUN_DIR/OVMF_VARS.fd" \
  -cdrom "$ISO" -boot order=d -nic none -display gtk \
  -serial "file:$RUN_DIR/uefi-serial.log" -no-reboot
```

Після завантаження в кожному режимі перейдіть на `tty2` (`Ctrl+Alt+F2`)
і перевірте:

1. Автоматичний вхід `wsm`; `locale` показує `uk_UA.utf8`.
2. Кирилиця й рамки TUI відображаються без відсутніх glyph-ів;
   `LatGrkCyr-8x16` застосований до `tty2`.
3. `Alt+Shift` перемикає US/UA в обидва боки; на US можна вводити шляхи,
   на UA клавіші `о/л` рухають вибір униз/угору, `й` завершує TUI.
4. `wsm-install-live` показує українські повідомлення; стрілки та `j/k`
   теж працюють. Preview повідомляє, що APPLY вимкнено й систему не встановлено.
5. Серійний журнал містить `WSM_LIVE_READY`. Після виходу з VM перевірте,
   що не було підключено віртуальний жорсткий диск, мережу або host passthrough.

До звіту додайте source commit, Guix lock commit, SHA-256 ISO, версію QEMU,
firmware mode, точну команду, serial log і результат кожного пункту.
QEMU TCG доводить лише поведінку емульованої машини, а не фізичну сумісність.

Довідка: [QEMU System Invocation](https://www.qemu.org/docs/master/system/invocation.html)
описує `-machine ... accel=tcg`, `-cdrom` та block-device options;
release workflow WSM окремо виконує BIOS/UEFI marker smoke.

## Межі

- У цьому RC доступні hardware preflight і перегляд плану; APPLY вимкнено
  в усіх entrypoints. Носій не розбиває диск, не форматує розділи, не монтує
  цільову систему та не запускає `guix system init`.
- Free ISO використовує автентифікований офіційний Guix lock; Nonguix і
  proprietary firmware не додаються.
- Це QEMU boot acceptance у BIOS і UEFI, а не підтвердження сумісності
  кожної фізичної конфігурації.
- Release workflow не публікує ISO розміром 2 GiB або більше.

## Відтворюваність

Збірка виконується на GitHub-hosted Ubuntu runner з
`systems/live-minimal.scm` і `channels.lock.scm`. У релізі є ISO,
build/release manifests, SHA-256 і результати BIOS/UEFI boot smoke.
