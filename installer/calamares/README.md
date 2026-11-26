# Calamares у WSM

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **preview-only; required job повертає failure, поки APPLY вимкнено**
- Роль: **опційний** вхід. Основний шлях — `wsm-install` (CLI): він працює там,
  де графічний майстер не піднімається (див. [INSTALLER.md](../../docs/INSTALLER.md))
- Рішення: [ADR 0008](../../docs/decisions/0008-calamares-backend-module.md) (`proposed`)

## Розподіл ролей

| Шар | Хто робить | Файл |
| --- | --- | --- |
| Мова, локація, клавіатура, користувач | Calamares, з коробки | — |
| Розбиття диска | Calamares (kpmcore) | — |
| Перевірка заліза й докази | **WSM** | `modules/wsm_deploy/main.py` |
| Вибір профілю | **WSM** | те саме |
| Preview системи | **WSM** | `wsm_install/install_steps.py` + preview-only `executor.py` |

Модуль навмисно тонкий: він не форматує й не монтує нічого сам, а викликає той
самий read-only planner, що й CLI. Поки APPLY не реалізований, required
`wsm_deploy` не може повернути `None` success після preview: Calamares має
зупинити job із повідомленням, що WSM не встановлено.

## Контракт jobmodule

- `run()` повертає failure tuple для preview, відсутнього `wsmDryRun` або false;
- `None` буде дозволений лише тоді, коли окремий reviewed APPLY реально встановить систему;
- failure tuple має форму `(message, details)`.

Модуль зараз ніколи не повертає `None`: навіть успішний preview завершується
failure tuple `WSM was not installed`. Це навмисно, бо Calamares трактує `None`
як успішне завершення required job. Відсутній звіт, невалідні докази, диск або
розмір також дають пояснювальний failure tuple.

## Ключі globalstorage, які читає модуль

| Ключ | Звідки | Навіщо |
| --- | --- | --- |
| `wsmReportPath` | крок preflight | звіт `wsm-hwcheck` |
| `wsmTargetDisk` | Calamares | цільовий диск; WSM ніколи не обирає сам |
| `wsmTargetSizeBytes` | Calamares | розмір — те, чим ловиться підмінений диск |
| `wsmProfileEvidence` | крок вибору профілю | bundle доказів заліза |
| `wsmSystemFile` | крок вибору профілю | який `.scm` віддати Guix |
| `wsmDryRun` | налаштування | прогін без запису |

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
