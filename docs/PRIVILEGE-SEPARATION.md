# Розділення привілеїв

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **preview-only; реальний запис на диск вимкнено**
- Код: [`wsm_install/agent.py`](../wsm_install/agent.py)
- Тести: `tests/test_agent.py`

## Призначення

UI і планувальник не повинні отримувати root лише для показу плану. Окремий
привілейований worker може перевірити структуру плану та allowlist команд,
але це саме по собі не доводить незмінність фізичного диска між плануванням і
виконанням.

Тому зараз worker **лише формує preview**. Виконання `partprobe`, `mkfs`,
`mount` та інших команд заблоковано для кожного виклику, навіть від root.

## Потік

1. Непривілейована частина може зберегти план у файл (`--write-plan plan.json`).
2. Worker читає план, перевіряє схему, allowlist, аргументи та кількість кроків.
3. Для preview потрібно явно передати `--dry-run`.
4. Без `--dry-run` worker повертає `agent.apply-disabled` до виклику executor.
5. `--recover` є read-only і потребує явного шляху до журналу; без нього повертається exit code 2.
6. У preview жодна команда з плану не виконується.

## Що відхиляється

| Відмова | Код | Причина |
| --- | --- | --- |
| програма поза allowlist | `agent.not-allowed` | UI не може передати shell або довільну програму |
| голе ім'я програми | `agent.not-allowed` | root не повинен шукати програму через змінний PATH |
| метасимвол оболонки в аргументі | `agent.shell-metacharacter` | аргумент не має перетворюватися на shell-команду |
| план не за схемою | `agent.bad-schema` | помилка виявляється до першого кроку |
| більше 32 кроків | `agent.too-many-steps` | план виходить за межі очікуваного інсталятора |
| запит реального виконання | `agent.apply-disabled` | відсутні stable device identity та digest-bound authorization |
| `--recover` без журналу | exit code 2 | звіт без джерела даних не формується |

## Allowlist preview

Перелік дозволених програм описує лише намір плану, який дозволено показати:

```
/usr/sbin/partprobe   /usr/bin/udevadm    /usr/sbin/mkfs.ext4
/usr/sbin/mkfs.btrfs  /usr/sbin/mkfs.xfs  /usr/sbin/mkfs.fat
/usr/bin/mount        /usr/bin/mkdir
```

Наявність команди в allowlist **не надає дозволу на виконання**.

## Межі й умови повернення APPLY

Worker не є пісочницею й поки не є дисковим executor-ом. Реальний APPLY може
повернутися лише окремим reviewed change, який доводить:

- стабільну identity block device і повторну перевірку перед кожною destructive boundary;
- незмінний typed plan із digest-bound consent;
- обмежений та перевірений набір виконуваних інструментів;
- перевірювані postconditions і контрольоване відновлення після переривання;
- destructive acceptance у disposable QEMU-дисках.

До виконання цих умов CLI, Guided, TUI, Calamares і privileged agent мають
однакову fail-closed політику.
