# Послідовність встановлення

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **не-виконуваний план; executor відсутній**
- Код: [`wsm_install/install_steps.py`](../wsm_install/install_steps.py)
- Джерело розкладки: [`wsm_install/partition.py`](../wsm_install/partition.py)
- Тести: `tests/test_install_steps.py`

## Що це

Модуль складає повну послідовність від запланованої GPT-розкладки до
підготовленого mount tree й фіксованого Guix handoff. Він повертає тільки
масиви аргументів та позначки destructive; жодної команди не запускає, не
відкриває block device й не монтує файлову систему.

`Layout` із partition planner описує **намір**, а не вже записану таблицю
розділів; він зберігає розмір диска на момент планування та точний шлях,
який користувач підтвердив. Підтвердження потрібне навіть для диска, позначеного
як порожній: `sgdisk --zap-all` усе одно замінює його partition table. Тому
install sequence спочатку включає `sgdisk --zap-all` і
створення всіх partition entries, і лише потім `partprobe` та `udevadm
settle`. `partprobe` перечитує наявну таблицю — він не створює GPT.

## Повний план UEFI для прикладу NVMe

Усі рядки нижче — лише preview. Кожний `sgdisk` і `mkfs` позначений як
**DESTRUCTIVE** у структурованому результаті.

```sh
sgdisk --zap-all /dev/nvme0n1
sgdisk --new=1:1MiB:513MiB --typecode=1:ef00 --change-name=1:wsm-esp /dev/nvme0n1
sgdisk --new=2:513MiB:0 --typecode=2:8300 --change-name=2:wsm-root /dev/nvme0n1
partprobe /dev/nvme0n1
udevadm settle
mkfs.ext4 -F /dev/nvme0n1p2
mkfs.fat -F 32 /dev/nvme0n1p1
mount /dev/nvme0n1p2 /mnt
mkdir -p /mnt/boot/efi
mount /dev/nvme0n1p1 /mnt/boot/efi
guix time-machine -C /run/wsm/channels.lock.scm -- system init /run/wsm/system.scm /mnt
```

## Запобіжники

**Підтвердження диска переноситься разом із розкладкою.** Partition planner
вимагає підтвердження, яке точно називає цільовий вузол, навіть якщо
інвентаризація позначила диск як порожній. `Layout` зберігає підтвердження та
спостережений розмір; якщо будь-яке з них втрачене, `plan_steps()` і
`backend_command()` відмовляють. Executor ще має повторно перевірити цей розмір
і block-device identity перед APPLY.

**Mount target фіксований.** Приймається лише точний `/mnt`; `/tmp`,
`/mnt2`, `/mnt/../root`, абсолютні альтернативи та шляхи з керівними
символами не нормалізуються «для зручності», а відхиляються.

**Жодного довільного Scheme-файлу.** Backend command закріплений за
`/run/wsm/system.scm`, канал — за `/run/wsm/channels.lock.scm`, target — за
`/mnt`. У preview використовується `guix time-machine -C ... -- system init
...`, а не ambient Guix із довільною ревізією каналів.

**Правильне ім'я розділу.** `/dev/sda` + 1 = `/dev/sda1`, але
`/dev/nvme0n1` + 1 = `/dev/nvme0n1p1`. Функція дозволяє лише відомі шаблони
whole-disk device path і додатний номер розділу.

**ESP усередині target.** UEFI ESP монтується в `/mnt/boot/efi`, не в
`/boot/efi` live-системи. BIOS layout має `bios_grub` partition та не
створює ESP/FAT filesystem.

## Чому ext4 типово

Бо він передбачуваний і має широку підтримку інструментів відновлення. btrfs
та XFS доступні як явні альтернативи з окремими аргументами форматування.
Файлова система не має обиратися приховано за користувача.

## Чого ще немає

- **Executor-а.** Немає коду, що запускає `sgdisk`, `mkfs`, `mount` або
  `guix system init`; ці операції не були виконані цим модулем.
- **Повторної ідентифікації block device перед APPLY.** Майбутній executor
  має звірити поточні major/minor, розмір та partition topology з
  підтвердженим планом безпосередньо перед першою мутацією.
- **Staging inputs.** Копіювання authenticated `channels.lock.scm` і
  згенерованого `operating-system` у `/run/wsm/` ще не реалізовано.
- **Перевірки після кожної фази та відновлення.** Потрібно зберігати журнал
  фаз і явно описати, що вже змінено, якщо процес обривається.
- **UUID у фінальній системній конфігурації.** Імена `/dev/...` тут
  використовуються для плану; майбутній `fstab`/boot configuration має
  прив'язуватися до перевірених filesystem UUID.
- **Guix end-to-end proof.** `guix system init` ще не запускався на
  disposable QEMU target; preview argv не є доказом успішного встановлення.

До появи цих перевірок послідовність — лише матеріал для огляду, не дозвіл
на запис у фізичний диск і не готовий інсталятор.
