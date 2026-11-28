# WSM Desktop — Minimal Live Installer Preview

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Це компактний live-носій на основі `systems/live-minimal.scm`: без KDE/Qt,
із мережею, апаратним preflight та власним WSM CLI/TUI. Він призначений для
завантаження WSM на слабкому обладнанні, збору локального звіту про пристрої
та відкриття майстра планування інсталяції.

> **Статус доказів:** цей документ описує поточний source-профіль у репозиторії. Він сам по собі не доводить, що раніше опублікований ISO містить ці самі зміни.
> Для конкретного ISO звіряйте `source_commit` у `release-manifest.json`, checksum образу та artifact-specific evidence у [реєстрі перевірених артефактів](VERIFIED-ARTIFACTS.md). Якщо manifest/evidence для конкретного артефакту відсутній, його відповідність поточному source лишається `unknown`.

## Що опубліковано зараз

Стан публікації релізів і збіг із тим, що очікує репозиторій, показує одна
команда: `python3 scripts/publication_state.py`. Що вона виводить, що вважає
`unknown` і як запускати її без мережі — [PUBLICATION-STATE.md](PUBLICATION-STATE.md).

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
Створіть приватний тимчасовий каталог і один **тимчасовий sparse qcow2 target**.
VM має бути на TCG, без мережі, фізичних дисків чи host passthrough.
Єдиний writable block device — цей файл у `$RUN_DIR`; ISO підключається як CD-ROM:

```sh
RUN_DIR="$(mktemp -d)"
chmod 700 "$RUN_DIR"
WSM_ISO_DIR="$RUN_DIR/build" WSM_LIVE_PROFILE=systems/live-minimal.scm make image-live-minimal
ISO="$RUN_DIR/build/wsm-desktop-live.iso"
test -L "$ISO" && test -s "$ISO"
qemu-img create -f qcow2 "$RUN_DIR/target.qcow2" 16G
TARGET_SHA_BEFORE="$(sha256sum "$RUN_DIR/target.qcow2" | cut -d " " -f1)"
```

BIOS-запуск:

```sh
qemu-system-x86_64 \
  -machine q35,accel=tcg -m 2048 -smp 2 \
  -drive if=none,id=target,file="$RUN_DIR/target.qcow2",format=qcow2 \
  -device virtio-blk-pci,drive=target \
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
  -drive if=none,id=target,file="$RUN_DIR/target.qcow2",format=qcow2 \
  -device virtio-blk-pci,drive=target \
  -cdrom "$ISO" -boot order=d -nic none -display gtk \
  -serial "file:$RUN_DIR/uefi-serial.log" -no-reboot
```

Після завантаження в кожному режимі перейдіть на `tty2` (`Ctrl+Alt+F2`) і перевірте:

1. Автоматичний вхід `wsm`; `locale` показує `uk_UA.utf8`.
2. Кирилиця й рамки TUI відображаються без відсутніх glyph-ів; `LatGrkCyr-8x16` застосований до `tty2`.
3. `Alt+Shift` перемикає US/UA в обидва боки; на US можна вводити шляхи, на UA клавіші `о/л` рухають вибір униз/угору, `й` завершує TUI на екрані навігації.
4. У списку цілей має бути тестовий `/dev/vda`. Введіть `/dev/vda` у підтвердженні. У цьому полі `q`, `j`, `k`, `й`, `о`, `л` є звичайними символами шляху; `Esc` скасовує введення. Regression tests окремо перевіряють `/dev/sdq`, `/dev/sdj` і `/dev/sdk`.
5. `wsm-install-live` показує українські повідомлення; стрілки та `j/k` теж працюють. Preview повідомляє, що APPLY вимкнено й систему не встановлено.
6. Серійний журнал містить `WSM_LIVE_READY`. Після завершення обох VM-запусків SHA-256 qcow2 має збігатися з `$TARGET_SHA_BEFORE`; WSM не змінював ціль. Мережа, фізичні диски й host passthrough не використовувалися.

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
- Один asset GitHub обмежений 2 GiB. Якщо образ більший, реліз містить
  **частини** (`*.iso.partNNN`) замість цілого файлу — див. нижче.

## Якщо образ опубліковано частинами

Склеювання виконується у **лексичному** порядку імен; інший порядок дасть
файл із правильним розміром і неправильним вмістом.

```sh
mkdir -p ~/wsm && cd ~/wsm
cat WSM-Desktop-*.iso.part* > WSM-Desktop.iso
sha256sum WSM-Desktop.iso
```

Далі звірте `sha256` із полем `artifact.sha256` у `release-manifest.json`.
Це sha256 **цілого** образу, а не частин: маніфест описує файл, який має
вийти після склеювання, з `artifact.published_as: "parts"`.

```sh
python3 -c "import json,hashlib,pathlib; m=json.loads(pathlib.Path('release-manifest.json').read_text()); print('збіг' if hashlib.sha256(pathlib.Path('WSM-Desktop.iso').read_bytes()).hexdigest() == m['artifact']['sha256'] else 'НЕ ЗБІГАЄТЬСЯ')"
```

Запис на USB — після збігу, не до:

```sh
sudo dd if=WSM-Desktop.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

`/dev/sdX` — це носій, а не розділ (`/dev/sdX1`). Помилка тут знищує чужі дані.

## Відтворюваність

Збірка виконується на GitHub-hosted Ubuntu runner з
`systems/live-minimal.scm` і `channels.lock.scm`. У релізі є ISO,
build/release manifests, SHA-256 і результати BIOS/UEFI boot smoke.

## Криптографічне походження артефактів

Після успішної збірки ISO, BIOS/UEFI marker smoke та повторної перевірки
завантажених із GitHub release assets workflow створює підписане SLSA v1
build-provenance через GitHub Artifact Attestations і Sigstore. Релізний workflow
дозволяє запуск лише з `refs/heads/main`; `gh attestation verify` вимагає CLI
не нижче `2.102.0`, оскільки старі версії мали помилку prefix-match у
`--signer-workflow` (GHSA-wjmr-j3rp-mh2g). Перевірка також фіксує точний
`--source-ref refs/heads/main`. Атестація
охоплює ISO, `SHA256SUMS`, build/release manifests і BIOS/UEFI evidence;
їхні digest пов'язуються з репозиторієм, commit і workflow signer.

Локальна перевірка завантаженого ISO:

```sh
gh attestation verify WSM-Desktop-0.1.0-rc6-Minimal-Live.iso \
  --repo juv4uk/wsm-desktop \
  --signer-workflow juv4uk/wsm-desktop/.github/workflows/release-minimal-live.yml
```

Атестація доводить походження digest від конкретного GitHub Actions workflow,
але сама по собі не доводить відтворюваність збірки, відсутність уразливостей
або сумісність із фізичним обладнанням. GitHub Artifact Attestations дає
SLSA Build Level 2 provenance; для Level 3 потрібен окремий ізольований
reusable workflow.
