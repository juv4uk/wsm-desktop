# Середовище розробки

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

## Загальні вимоги

Для повної перевірки потрібні GNU Guix, Linux environment та QEMU. Розробляти документацію можна на будь-якій системі, але build/boot/installer tests повинні завершуватися у Linux VM або на окремому тестовому обладнанні.

Не використовуйте фізичний диск із цінними даними для експериментів з інсталятором.

## Перевірка репозиторію

З кореня репозиторію:

    make check

Команда запускає автоматичні Python-перевірки, перевірку документації, схем, installer contracts та структурних channel locks. Вона не збирає Guix System, ISO й не запускає QEMU guest.

## Повільні acceptance — лише вручну

Звичайний `make check` і hosted CI не встановлюють QEMU/Guix та не запускають гостьові системи. Коли потрібна runtime-перевірка, запускайте її явно:

    make qemu-acceptance-manual
    make check-guix-eval

Для перевірки конкретного ISO використовуйте `python scripts/qemu_boot_smoke.py --iso /absolute/path/to/image.iso`. Деталі й межі доказів — у [ручних QEMU runtime-перевірках](testing/QEMU-GUEST-CI.md).

## Guix bring-up

Перевірте доступність Guix:

    guix --version
    guix describe

Якщо в PATH одночасно є Nix та системний Guix (WSL з обома менеджерами),
`guix` може вказувати на Nix-профіль. Для перевірок WSM завжди
викликайте системний бінарник явно:

    /usr/local/bin/guix --version

Це не змінює Nix і не перемикає його профілі.

Поточний мінімальний приклад можна спробувати побудувати:

    make check-system

Або без Make:

    guix system build systems/minimal.scm

Для побудови VM wrapper:

    make vm-system

Команда guix system vm будує VM-образ/запускний скрипт відповідно до параметрів Guix. Вона не встановлює систему на фізичний диск.

## Guix package manager на наявному GNU/Linux

Коли потрібно встановити **лише package manager GNU Guix** на вже наявний
foreign GNU/Linux distribution, використовуйте офіційний upstream
[`guix-install.sh`](https://guix.gnu.org/guix-install.sh), а не окремий
WSM-owned root bootstrap:

```sh
cd /tmp
wget https://guix.gnu.org/guix-install.sh
chmod +x guix-install.sh
less guix-install.sh
sudo ./guix-install.sh
```

Це root-level операція, яка налаштовує Guix store та daemon. Застосовуйте її
лише на системі, де Guix ще не встановлено, після перевірки поточного скрипта
та офіційної [Binary Installation документації](https://guix.gnu.org/manual/en/html_node/Binary-Installation.html).
Не запускайте цей foreign-distro installer поверх наявної Guix installation.

Цей шлях **не встановлює повну Guix System**: для неї призначено окремий
[System Installation розділ](https://guix.gnu.org/manual/en/html_node/System-Installation.html)
та Guix System installer flow. Він також не створює WSM channel
`.guix-authorizations`, introduction commit, keyring чи authenticated consumer.
WSM CI/release workflow налаштовує власний одноразовий runner окремо.

## Фіксація каналів

Перед відтворюваним експериментом збережіть опис реально використаних каналів:

    guix describe -f channels > channels.lock.scm

Перегляньте результат, перевірте ревізії та підписи, після чого додайте snapshot окремим комітом. Не вигадуйте commit hashes і не використовуйте рухому гілку як релізний lock.

channels/free.scm описує вільний набір каналів. channels/compatibility.scm додає Nonguix як явну опцію. Сам факт наявності compatibility.scm не означає автоматичного встановлення nonfree kernel чи firmware.

## Безпечні тестові диски

Для інтеграційних тестів створюйте окремий одноразовий qcow2 диск у QEMU. Перед запуском перевіряйте, що віртуальна машина не має підключення до реальних дисків хоста.

Не виконуйте guix system init з /mnt або іншою ціллю на реальній машині, доки не буде завершено code review та інтеграційні тести WSM adapter.


## Hardware report schema tests

Install the pinned development validation dependency and run the full checks:

    python3 -m pip install -r requirements-dev.txt
    make check

The hardware report contract uses JSON Schema Draft 2020-12. The test suite validates the schema, all synthetic fixtures, the local-only privacy invariants, and the rule that unknown observations are not treated as failures.

## Перевірка Scheme на раннері

`systems/*.scm` ніколи не виконувались: у середовищі розробки немає Guix. Саме
тому пропущений `(srfi srfi-1)` доїхав до main — файл читається очима, а падає
на завантаженні.

``make check-guix-eval` (manual, needs Guix)` закриває це: раннер ставить Guix, авторизує
ключ підстановок і виконує

```sh
guix time-machine -C channels.lock.scm -- system build systems/desktop.scm --dry-run
```

`--dry-run` розв'язує весь граф і **вимагає прочитати й обчислити файл**, але не
завантажує жодного пакета. Це ловить відсутні імпорти, невідомі поля записів і
зламане спадкування за кілька хвилин.

`systems/compatibility.scm` навмисно **не** перевіряється: він потребує Nonguix,
якого в `channels.lock.scm` немає, і додавати невільний канал у CI означало б
змінити політику проєкту заради зручності перевірки.
