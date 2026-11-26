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
| Розбиття диска | Calamares (kpmcore) | — |
| Перевірка заліза й докази | **WSM** | `modules/wsm_deploy/main.py` |
| Вибір профілю | **WSM** | те саме |
| Планування / preview системи | **WSM** | `wsm_install/install_steps.py` + `executor.py` |

Модуль навмисно тонкий: він не форматує й не монтує нічого сам, а викликає ті
самі модулі, що й CLI. Одна реалізація кожної небезпечної операції, Calamares —
лише обличчя.

## Поточна безпекова межа

Модуль Calamares поки **не встановлює систему**. Він передає typed plan до
спільного preview-only executor. Якщо глобальний ключ wsmDryRun дорівнює false,
executor повертає execute.apply-disabled; модуль повертає помилку jobmodule.
Calamares не має окремого шляху до sgdisk, mkfs, mount чи guix system init.

Ця межа однакова для CLI, --guided і --tui. Повторне введення шляху диска
підтверджує лише вибір цілі для preview, а не destructive consent. Реальний
APPLY потребуватиме окремого reviewed контракту, перевірки block-device
identity та destructive acceptance на одноразових QEMU-дисках.

## Контракт jobmodule

- `run()` повертає `None` при успіху;
- при збої — кортеж `(message, details)`: короткий рядок для людини й довший
  текст для журналу.

Модуль ніколи не повертає `None`, якщо чогось бракує. Відсутній звіт про залізо,
невирішений блокер, невалідні докази, відсутній диск або розмір — усе це кортеж
з поясненням.

Усі frontend-и зараз завершуються read-only preview. Розмір у globalstorage
використовується для розрахунку макета, а не для підтвердження фактичної
місткості пристрою: модуль не читає block-device identity або sysfs topology.

## Ключі globalstorage, які читає модуль

| Ключ | Звідки | Навіщо |
| --- | --- | --- |
| `wsmReportPath` | крок preflight | звіт `wsm-hwcheck` |
| `wsmTargetDisk` | Calamares | цільовий диск; WSM ніколи не обирає сам |
| `wsmTargetSizeBytes` | Calamares | введена оцінка для побудови layout; не вимірює block device |
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
