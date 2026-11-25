# Середовище розробки

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

## Загальні вимоги

Для повної перевірки потрібні GNU Guix, Linux environment та QEMU. Розробляти документацію можна на будь-якій системі, але build/boot/installer tests повинні завершуватися у Linux VM або на окремому тестовому обладнанні.

Не використовуйте фізичний диск із цінними даними для експериментів з інсталятором.

## Перевірка репозиторію

З кореня репозиторію:

    make check

Команда перевіряє внутрішні Markdown-посилання. Вона не є перевіркою Guix-конфігурації.

## Guix bring-up

Перевірте доступність Guix:

    guix --version
    guix describe

Поточний мінімальний приклад можна спробувати побудувати:

    make check-system

Або без Make:

    guix system build systems/minimal.scm

Для побудови VM wrapper:

    make vm-system

Команда guix system vm будує VM-образ/запускний скрипт відповідно до параметрів Guix. Вона не встановлює систему на фізичний диск.

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

`.github/workflows/guix-eval.yml` закриває це: раннер ставить Guix, авторизує
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


## Паралельна розробка, агенти й злиття

Перед початком роботи перевірте [реєстр рішень](DECISIONS.md), актуальний
`main`, пов'язані issue та вже відкриті PR. Один канонічний issue має один
власний deliverable; не створюйте конкуруючі PR з однаковим результатом.
Якщо нова гілка замінює стару, старий PR закривається як superseded із
посиланням на canonical PR.

Перед завершальним review:

1. Синхронізуйте гілку з поточним `main`; перевірте base/head SHA та список
   змінених файлів. «Mergeable» не означає, що зміна актуальна або перевірена.
2. Перегляньте повний diff і acceptance criteria канонічної задачі. Для
   міграцій, installer, firmware та профілів перевіряйте також негативні
   сценарії й межі того, чого зміна **не** доводить.
3. Вимагайте успішні checks саме для останнього commit SHA PR. `queued`,
   `pending`, скасована перевірка або green CI попереднього SHA не є
   успішним gate. Будь-який новий push після перевірки інвалідує попередній
   exact-head результат.
4. Не обходьте review/CI та не надавайте агентам необмежений bypass. Доступ
   агента має відповідати задачі; команди з дисковими, firmware, bootloader
   або мережевими side effects залишаються окремими явно авторизованими кроками.
5. У PR описуйте фактично виконані команди, exit codes, artifact hashes і
   обмеження. Не перетворюйте «код написано» або «CI queued» на твердження
   «функція перевірена».

Практичний урок Omarchy 4.5 такий самий: велика кількість паралельних внесків
дає швидкість лише тоді, коли інтеграційні межі та перевірки сильні. Їхні
release notes документують міграції, що зависали на зовнішніх tool lookups,
невдалі апдейти, помилки boot handoff та регресії конфігурацій
([Omarchy 4.5 release notes](https://omarchy.org/news/2026/11/omarchy-4-5/)).
WSM не повинен виправляти такі проблеми постфактум через серію дублікатів PR:
один owner, один canonical issue, один перевірений head.

