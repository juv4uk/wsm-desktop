# Послідовність встановлення

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **план реалізовано, нічого не виконується**
- Код: [`wsm_install/install_steps.py`](../wsm_install/install_steps.py)
- Тести: `tests/test_install_steps.py` (19)

## Що це

Між «диск розбито» і «Guix пише систему» є кроки, кожен з яких може зіпсувати
встановлення тихо. Модуль будує їхній список як дані — з поясненням навіщо і з
позначкою, які з них знищують дані.

```
partprobe /dev/nvme0n1          # safe
udevadm settle                  # safe
mkfs.ext4 -F /dev/nvme0n1p2     # DESTRUCTIVE
mkfs.fat -F 32 /dev/nvme0n1p1   # DESTRUCTIVE
mount /dev/nvme0n1p2 /mnt       # safe
mkdir -p /mnt/boot/efi          # safe
mount /dev/nvme0n1p1 /mnt/boot/efi
guix system init systems/desktop.scm /mnt
```

## Контракт Guix executable closure

Планувальник ідентифікує утиліти закритим allowlist і на фактичній Guix System
резолвить кожну лише за точним шляхом у
`/run/current-system/profile/bin` або `/run/current-system/profile/sbin`.
Він не використовує успадкований `PATH`, FHS `/usr/bin`/`/usr/sbin`, user
profile чи host fallback. Відсутній, неоднозначний або невиконуваний executable
дає типізовану fail-closed відмову.

Обидва Free live-профілі явно включають `gptfdisk`, `parted` і `dosfstools`;
locked Guix check будує саме ці пакети з `channels.lock.scm`. На звичайному
non-Guix розробницькому host planner може показати лише логічні basename names
як дані preview. Це не виконувані шляхи: privileged agent приймає лише точні
Guix system-profile paths і відхиляє bare names та старі FHS aliases.

Блок команд вище — пояснювальна форма argv, а не готовий shell script. Реальний
planner також включає явні GPT partition-table кроки перед `partprobe`; кожен
такий крок позначено destructive. Shared executor лише показує `not-run` для
кожного кроку. Команди не запускаються, диск не відкривається для запису, а
`APPLY` залишається вимкненим у CLI, Calamares і privileged agent.

## Три помилки, які цей порядок виключає

**Форматування застарілого вузла.** Ядро не завжди помічає нові розділи. Без
`partprobe` перед `mkfs` можна відформатувати те, чого вже немає, або не те.

**Завантажувач на live-системі.** ESP треба монтувати **всередину** цілі
(`/mnt/boot/efi`), а не поруч. Інакше GRUB ставиться в ESP живої системи, і
встановлення «успішне», але завантажитись нема з чого.

**Неправильне ім'я розділу.** `/dev/sda` + 1 = `/dev/sda1`, але
`/dev/nvme0n1` + 1 = `/dev/nvme0n1p1`. Помилка тут форматує **диск** замість
розділу. Ім'я обчислюється в одному місці й покрите тестами.

## Чому перший Guix target приймає лише ext4

`systems/desktop.scm` фіксує root filesystem як ext4. Тому перший preview
приймає лише ext4 і відхиляє btrfs/xfs: інакше планувальник міг би
відформатувати root одним типом, тоді як Guix target монтував би його як інший.
Це не твердження, що btrfs або xfs технічно непридатні. Вони повернуться до
вибору після реалізації та перевірки versioned Guix system-config generator,
який узгоджує formatter argv, root declaration, package closure та QEMU
acceptance в одному typed contract.

## Чого ще немає

- **Виконання.** Модуль не запускає нічого; списком команд розпоряджається
  викликач.
- **Перевірки після кожного кроку.** План не читає, що вийшло: чи створився
  розділ, чи змонтувався корінь.
- **Перевірки, що `guix system init` узагалі існує в цій версії Guix.** Команда
  відповідає документації, але жодного разу не виконувалась.
- **UUID замість імен.** `/dev/nvme0n1p2` може стати `/dev/nvme0n2p2` після
  перезавантаження; для `fstab` і завантажувача потрібні UUID, і це окрема
  робота.
- **Відкату.** Якщо `guix system init` упав посередині — план відновлення не
  описаний.
