# Calamares у WSM

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **модуль написано, у Calamares не запускався**
- Роль: **опційний** вхід. Основний шлях — `wsm-install` (CLI): він працює там,
  де графічний майстер не піднімається (див. [INSTALLER.md](../../docs/INSTALLER.md))
- Рішення: [ADR 0008](../../docs/decisions/0008-calamares-backend-module.md) (`proposed`)

## Розподіл ролей

| Шар | Хто робить | Файл |
| --- | --- | --- |
| Мова, локація, клавіатура, користувач | Calamares, з коробки | — |
| Розбиття диска | план WSM як дані; Calamares partition module ще не налаштований | — |
| Перевірка заліза й докази | **WSM** | `modules/wsm_deploy/main.py` |
| Вибір профілю | **WSM** | те саме |
| План і preview | **WSM** | `wsm_install/install_steps.py` + preview-only `executor.py` |

Модуль навмисно тонкий: він не форматує й не монтує нічого сам, а викликає ті
самі модулі, що й CLI. Одна реалізація планування; наразі всі небезпечні операції вимкнено, Calamares — лише optional frontend.

## Контракт jobmodule

- `run()` повертає `None` при успіху;
- при збої — кортеж `(message, details)`: короткий рядок для людини й довший
  текст для журналу.

Модуль ніколи не повертає `None`, якщо чогось бракує. Відсутній звіт про залізо,
невирішений блокер, невалідні докази, відсутній диск або розмір — усе це кортеж
з поясненням.

## Ключі globalstorage, які читає модуль

| Ключ | Звідки | Навіщо |
| --- | --- | --- |
| `wsmReportPath` | крок preflight | звіт `wsm-hwcheck` |
| `wsmTargetDisk` | Calamares | цільовий диск; WSM ніколи не обирає сам |
| `wsmTargetSizeBytes` | Calamares | user-supplied оцінка для плану; не вимірюється з block device |
| `wsmProfileEvidence` | крок вибору профілю | bundle доказів заліза |
| `wsmSystemFile` | крок вибору профілю | який `.scm` віддати Guix |
| `wsmDryRun` | налаштування | boolean; preview завершується явною non-success відповіддю, false — APPLY refused |

## Чому модуль сам шукає `wsm_install`

Calamares завантажує `main.py` за шляхом, тому пакет не імпортується. Модуль
піднімається вгору по батьківських теках, доки не знайде `wsm_install`, замість
того щоб вгадувати фіксовану глибину.

## Чого ще немає

- **Запуску в Calamares.** Жодного разу: ні збірки модуля, ні прогону в живому
  інсталяторі.
- **`settings.conf`.** Порядок кроків у Calamares ще не описаний: спершу треба
  вирішити, які його власні модулі ми лишаємо (partition, users, locale), а які
  вимикаємо.
- **Кроку preflight як окремого модуля.** Зараз `wsmReportPath` має заповнити
  хтось інший; цей модуль лише читає його.
- **QML-інтерфейсу вибору профілю.**

## Поточна межа APPLY

Preview не повертає Calamares `None` як успіх: job повертає явну помилку зі статусом, що система **не встановлена**. Будь-який реальний APPLY залишається вимкненим до target-bound executor, digest-bound consent, перевіреної Guix tool closure та disposable-QEMU acceptance.
