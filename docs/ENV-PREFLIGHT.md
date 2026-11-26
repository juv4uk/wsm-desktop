# Перевірка середовища перед встановленням

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **реалізовано, на реальному залізі не запускалось**
- Код: [`wsm_install/preflight_env.py`](../wsm_install/preflight_env.py)
- Тести: `tests/test_preflight_env.py` (17)

## Навіщо

Інсталятор має багато способів зламатися з причин, які не стосуються цільового
диска: немає `mkfs.fat`, немає `guix`, `/mnt` уже зайнятий, системного файлу
немає. Кожна з них дешево виявляється **до** першого кроку і дорого — на п'ятому
з семи, після того як диск уже стерто.

```sh
wsm-install --preflight --dry-run --report hw.json --backend guix --check-env
```

## Що перевіряється

| Перевірка | Що ловить |
| --- | --- |
| `tools` | усі програми з allowlist агента існують |
| `guix` | без нього систему можна записати, але не зібрати |
| `root` | без root форматування й монтування проваляться |
| `mount-point` | точка монтування не існує, вже змонтована або не порожня |
| `system-file` | файл є і справді містить `operating-system` |
| `report` | звіт `wsm-hwcheck` читається і має очікувану схему |
| `isa` | рівень CPU — як доказ, не як умова |

## Чому `mount-point` важливіший, ніж здається

Якщо `/mnt` уже є точкою монтування, нова система ляже **під** старою, і
виглядатиме це як «встановлення пройшло, але завантажується старе». Якщо в теці
щось лежить, воно зникне з-під очей при монтуванні.

## Приклад прогону

```
overall: fail
  tools        fail   missing: /usr/bin/udevadm, /usr/sbin/mkfs.fat, ...
  guix         fail   guix is not in PATH; the system could be written but not built
  root         fail   not running as root; formatting and mounting will fail
  mount-point  pass   /mnt is free
  system-file  pass   systems/desktop.scm declares an operating-system
  report       pass   2 device(s) in the report
  isa          pass   highest supported level: x86-64-v2
```

Це справжній прогін у середовищі розробки: там справді немає ні `guix`, ні
`mkfs`, і перевірка це каже прямо, замість того щоб впасти на третьому кроці.

## Чого не перевіряє

- **Ідентичність цільового диска.** Цей preflight не читає block-device identity. Параметр `--target-size-bytes` є введеною користувачем оцінкою для плану; фактичні capacity, major/minor, serial/WWN і sysfs topology наразі не вимірюються.
- **Що вистачить місця** під повний store Guix.
- **Що мережа працює** — потрібна для завантаження замін.

Поточний інсталятор є preview-only: успішний env-preflight не дозволяє APPLY і не доводить, що цільовий диск правильно ідентифіковано. Не запускати запис до появи окремого target-bound протоколу та disposable-QEMU acceptance.
