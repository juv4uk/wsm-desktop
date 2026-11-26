# Уроки Omarchy

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **аналіз**, правила виконуються тестом `tests/test_repo_hygiene.py`
- Застосовано до: [INSTALL-SEQUENCE.md](INSTALL-SEQUENCE.md), [PARTITIONING.md](PARTITIONING.md), [HARDWARE-PROFILE-EVIDENCE.md](HARDWARE-PROFILE-EVIDENCE.md)

Omarchy — проєкт, у якому теж працювали агенти. Корисно подивитися не на те, що
в них вийшло, а на те, що вони отримали у відповідь від користувачів. Майже вся
критика там стосується не смаків, а інженерних рішень.

## Що критикували

**«438 із 443 команд — це bash-скрипти».** Претензія не до мови, а до того, що
шар між користувачем і системою виріс без тестів і без інтерфейсів. [1]

**«Клей, який встановлює, оновлює, мігрує і підштовхує залізо, — це купа
крихких скриптів».** [2]

**«Це AI slop wrappers».** [2] Найболючіше в цьому те, що закид стосується не
якості коду, а **відсутності перевірки**: ніхто не може сказати, чи воно працює.

**Встановлення через завантаження й одразу виконання в оболонці.** Окремо і
повторювано: людина не бачить, що саме запускає. [3]

## Що вони зробили правильно

**Міграції як окремий шар.** Оновлення пакета не може виправити стан, який
pacman не вміє володіти: перевключити службу, переписати формат налаштувань,
прибрати мертвий симлінк. Omarchy зробив `migrations/*.sh` з обов'язковою
ідемпотентністю і відстеженням завершення **на користувача** — бо на ноутбуці з
двома акаунтами другий теж має отримати виправлення. [1]

Це рішення з болю, а не з теорії. І воно стосується нас: у Guix покоління
атомарні, але **дані користувача і формати наших власних артефактів** ніхто не
мігрує.

## Що з цього беремо

| Правило | Як виконується |
| --- | --- |
| Жодного завантаження з негайним виконанням в оболонці — ні в документації, ні в скриптах | тест забороняє шаблон |
| Python не передає команди на інтерпретацію shell | AST policy з alias-aware перевіркою `os.system/popen`, `subprocess(..., shell=True)` та `asyncio.create_subprocess_shell` |
| Кожен shell-скрипт мусить синтаксично розбиратися | `bash -n`; це не є доказом runtime-коректності |
| Поведінку script перевіряє focused test або CI workflow, який реально його запускає | behavioral test / QEMU acceptance; згадка імені файла не є покриттям |
| Новий шар — це модуль із типами й тестами, а не ще один bash-обгортанець | рев'ю |
| Кожен артефакт має версію схеми, і читач відмовляє на невідомій | `wsm-cpu-isa/1`, `wsm-perf-baseline/1`, `wsm-profile-evidence/1`, `wsm-release-verdict/1` |

## Що з цього вже зроблено в нас

- Усі модулі інсталятора — Python із типами й тестами; bash немає взагалі.
- Артефакти версійовані, і кожен валідатор відмовляє на невідомій версії.
- Докази заліза мають обов'язкове поле «що не перевірено».

## Що лишається ризиком

**Міграції наших власних артефактів.** Коли `wsm-profile-evidence/1` стане
`/2`, старі bundle перестануть проходити. Плану міграції немає. Це та сама
проблема, яку Omarchy вирішив скриптами; у нас вона поки не виникла лише тому,
що реальних bundle ще немає.

**Спокуса рахувати файли замість перевірок.** Кількість scripts і tests не
доводить їхню якість. У `tests/test_repo_hygiene.py` більше немає filename-only
coverage чи перевірки текстових маркерів замість виконання. AST policy виявляє
відомі shell-interpreting API з урахуванням alias imports, а fixtures перевіряють
alias bypass, `shell=True`, багаторядкові download-to-shell pipes і безпечне
завантаження у файл. `bash -n` лишається лише syntax check; поведінку shell
harness підтверджує окремий QEMU CI job.

---

1. Shaun Li, «Omarchy 4.0: The Distro Is Mostly a Migration Runner», 2026-08-18.
2. Starry Hope, «How Omarchy Stacks DHH's Defaults on Arch, Hyprland, and Quickshell».
3. andmc.ca, «Omarchy: The Distro That Thinks It's a Revolution», 2025-10-21.

## Безпека: що саме зламалося в 4.0.0

У 4.0.1 вийшло одинадцять виправлень безпеки. Три з них стосуються нас прямо.

**PATH у привілейованому хелпері.** DNS-хелпер запускався від root з
успадкованим `PATH`, і тек-каталог користувача, що стояв раніше в `PATH`, міг
підсунути файл з іменем стандартної утиліти — він виконувався від root
(виправлено #8172).

**Рядок замість argv.** Назва відео з вебсторінки потрапляла в команду, яку
виконував bash: спершу через `printf %q` на шляху, потім — гірше — через
D-Bus-підказку, яку Quickshell виконував як `bash -lc <рядок>`. Кожен виклик
мусив сам подбати про екранування, і кожен, хто забув, відкривав ту саму діру.
Стійке виправлення (#7926) прибрало shell із ланцюга взагалі: підказка стала
JSON-масивом аргументів, який передається як `"$@"`.

**Третій бік — це виконання коду.** Тема, встановлена з чужого git-репозиторію,
приносила `.lua`-файли й конфіги терміналів, які потім виконувались як
користувач (CVE-2026-108913, CVSS 7.1). Різниця між «тема, яку написав ти» і
«тема, яку написав незнайомець» ніде не перевірялась.

## Що з цього зроблено в нас

| Урок | Наше рішення |
| --- | --- |
| PATH-підміна у привілейованому кроці | усі команди в `install_steps.py` — абсолютні шляхи з фіксованої таблиці; тест забороняє голе ім'я |
| Рядок замість argv | команди — списки аргументів; тест забороняє `shell=True`, `os.system`, `os.popen` у наших модулях |
| Третій бік як виконання коду | Nonguix винесено в окремий профіль Compatibility, поза вільним деревом і поза live-образом |

Третій пункт варто сформулювати як правило: **сторонній канал — це виконання
коду, тому він має бути названий, зафіксований і автентифікований**. Це не
заборона Nonguix: продукт WSM навмисно постачає пропрієтарні драйвери. Це
заборона каналу, про який ніхто не знає, звідки він і на чому стоїть.

## Чого в нас досі немає

**Політики відповідального розкриття з термінами.** У Omarchy є окрема сторінка
`/security` і команда, що розбирає звіти. У нас SECURITY.md описує процес, але
не обіцяє строків.

**Перевірка channel policy вже входить у `make check`, але її строгість ще
потребує посилення.** Поточний `check-channels` запускає обидві політики, однак
старий checker використовує один default lock для Free та Compatibility і
дозволяє ширші host-based правила замість точних repository URL та повної
перевірки типів Scheme-полів. Застарілий PR [#263](https://github.com/juv4uk/wsm-desktop/pull/263)
закрито без merge; його відкритий successor [#276](https://github.com/juv4uk/wsm-desktop/pull/276)
ще потребує синхронізації з current main та exact-head CI. До його merge ці
вимоги не є властивістю main. Structural PASS не є криптографічною
автентифікацією: її окремо виконує Guix з увімкненим channel authentication.


## Оновлення аналізу: Omarchy 4.5 (листопад 2026)

Офіційний анонс Omarchy 4.5 опублікований 4 листопада, а GitHub позначає
`v4.5.0` як latest stable release від 5 листопада 2026 року. Команда повідомляє
про понад 740 merged PR від 180+ contributors за 12 тижнів. Це сильна швидкість
розробки, але кількість PR не замінює acceptance і не є аргументом копіювати
весь стек.

**Що варто вивчити, а не переносити буквально:**

- **Prebuilt root image замість сотень окремих package installs.** Omarchy 4.5
  описує скорочення інсталяції приблизно вдвічі після переходу від встановлення
  близько 940 пакетів по одному до розпакування prebuilt root image з подальшою
  machine-specific конфігурацією. Для WSM кандидат — відтворюваний Guix system
  output або кешована derivation з точними source/lock/profile hashes, а не
  непрозорий rootfs без provenance. До acceptance потрібні manifest, checksums,
  package closure і disposable-QEMU boot саме цього artifact.
- **Події замість зайвого polling.** Omarchy повідомляє про перехід частини UI
  на реакцію на зміни замість періодичних опитувань. У WSM використовувати
  D-Bus/udev та інші стабільні події там, де це реально зменшує навантаження;
  не додавати watcher, якщо він дублює власника транзакції або створює гонки.
- **Кілька режимів без втрати основного сценарію.** Omarchy 4.5 поєднує tiling
  і floating desktop modes, додає 50 мов та ARM install targets. Для WSM це
  нагадування розділяти desktop UX, system locale, UI language та input method,
  а архітектурну підтримку розширювати лише після package closure та реальних
  device acceptance. Поточний WSM vertical slice залишається x86_64/UEFI;
  KDE Plasma/Guix не треба замінювати на Hyprland/Arch лише заради наслідування.
- **Agent features не повинні обходити security model.** Omarchy 4.0.1
  замінив повний permission bypass для Claude/Codex на auto-review. Це підтримує
  правило WSM: агентська автоматизація має працювати в межах явної авторизації,
  журналювання та target-bound consent; «агент сказав, що все завершив» не є
  доказом.
- **Секрети й тимчасовий привілейований state мають мати власника.** Пізніші
  Omarchy fixes охопили пароль у RDP argv, state у world-writable `/tmp`,
  cleanup inhibitor-ів не тим процесом і sudo expiry після suspend. Для WSM:
  секрети не передавати в argv/logs; runtime state тримати в приватному
  UID-owned каталозі; cleanup прив'язувати до creator/owner; privilege lease
  має мати чіткий expiry та перевірку після suspend/resume.

**Конкретні regression classes з першоджерел:**

- [#6951](https://github.com/omacom/omarchy/pull/6951) — `root=` був втрачений
  під час package/kernel transaction; merged 3 жовтня 2026.
- [#14949](https://github.com/omacom/omarchy/pull/14949) — factory reset
  видаляв boot entries інших ОС на shared ESP; merged 20 жовтня 2026.
- [#14874](https://github.com/omacom/omarchy/pull/14874) — resume LUKS key change
  помилково міг видалити slot, доданий власником як recovery key; merged.
- [#16421](https://github.com/omacom/omarchy/pull/16421) — unresolved migration
  не повинна отримувати completion marker; merged.
- [#20178](https://github.com/omacom/omarchy/issues/20178) — open issue про
  Legacy/CSM multi-disk install без перевіреного boot-order handoff.

## Реєстр регресійних класів WSM

Кожен клас вище перетворений на правило й на перевірку — або чесно позначений як
непокритий. Статуси закриті: `covered`, `partial`, `not-covered`, `out-of-scope`.
Формат доказу — `tests/<file>::<test_method>`; 
`tests/test_omarchy_regression_register.py` перевіряє, що кожен заявлений
тест справді існує, а `make check-regression-register` запускає цю перевірку
в основному gate наборі.

| Клас | Prevent rule у WSM | Detect rule | Статус | Доказ |
| --- | --- | --- | --- | --- |
| PATH-підміна у привілейованому кроці (Omarchy #8172) | усі команди — абсолютні шляхи з фіксованої таблиці | тест перевіряє кожну команду плану | `covered` | `tests/test_install_steps.py::test_every_command_starts_with_an_absolute_path` |
| Рядок замість argv (Omarchy #7926) | команди — списки аргументів; shell-API заборонені в модулях | AST-policy замість пошуку рядків | `covered` | `tests/test_repo_hygiene.py::test_project_modules_do_not_use_shell_interpreting_apis` |
| Невільна залежність потрапляє до Free payload (WSM policy) | Nonguix лише в окремому Compatibility-профілі; Free channel відхиляє його | політика каналів перевіряє розділення профілів | `covered` | `tests/test_check_channels.py::test_nonguix_is_refused_by_free_policy` |
| Неперевірена тема/плагін виконує код (Omarchy CVE-2026-108913) | WSM поки не має механізму встановлення сторонніх тем/плагінів; поява такого механізму вимагатиме окремого threat review, provenance та явної згоди | немає такого install/execution path у поточному дереві | `out-of-scope` | — |
| Дія на застарілому стані (partition table після запису) | таблиця перечитується перед форматуванням | тест перевіряє порядок кроків | `covered` | `tests/test_install_steps.py::test_partition_table_is_reread_before_formatting` |
| USB device metadata виконується як Hyprland Lua (Omarchy #8129) | WSM не реалізує Hyprland device-toggle або генерацію Lua з USB descriptors | відповідної інтеграції в WSM немає | `out-of-scope` | — |
| FIDO2 migration передчасно позначається завершеною без виконання precondition (Omarchy #16421) | майбутній WSM migration runner має лишати невирішені preconditions у pending; власного FIDO2 migration runner поки немає | відповідну migration-підсистему WSM не реалізовано | `out-of-scope` | — |
| Видалення чужих boot entries на shared ESP (Omarchy #14949) | ESP монтується всередину цілі; чужий ESP не форматується | частково: тест перевіряє mountpoint, а не вміст ESP | `partial` | `tests/test_install_steps.py::test_esp_is_mounted_inside_the_target_not_outside` |
| `root=` втрачено під час kernel/package transaction (Omarchy #6951) | bootloader-конфіг генерує Guix System; WSM не пише `root=` сам | немає — WSM не має власного boot-кроку | `out-of-scope` | — |
| LUKS recovery slot видалено при зміні ключа (Omarchy #14874) | шифрування не реалізоване | немає коду, який чіпає slots | `out-of-scope` | — |
| Legacy/CSM multi-disk boot-order hand-off (Omarchy #20178) | BIOS layout створює `bios_grub`, але preview не доводить, що firmware після майбутнього встановлення стартує з цільового диска | немає двохдискового Legacy/CSM QEMU або physical acceptance | `not-covered` | — |
| Міграція власних артефактів (`wsm-profile-evidence/1` → `/2`) | плану міграції немає | немає | `not-covered` | — |

`out-of-scope` не означає «вирішено»: це означає, що коду, який міг би зламатися
саме так, у WSM поки немає. Щойно з'явиться власний boot-крок, шифрування,
механізм встановлення сторонніх тем/плагінів або друга версія артефакту —
відповідний рядок переходить у `not-covered` і отримує тест. Це також стосується майбутнього FIDO2 або іншого системного migration workflow.

Ці upstream reports — не докази дефектів у WSM або на конкретному обладнанні.
Це джерела для regression fixtures та acceptance вимог; кожен сценарій має
окремий prevent/detect rule і статус власної перевірки.

Джерела: [Omarchy 4.5 announcement](https://omarchy.org/news/2026/11/omarchy-4-5/),
[official v4.5.0 release](https://github.com/omacom/omarchy/releases/tag/v4.5.0),
[update process](https://github.com/omacom/omarchy/blob/quattro/docs/update-process.md),
[migration guide](https://github.com/omacom/omarchy/blob/quattro/agents/skills/migrations.md),
[Omarchy 4.0.1 security release](https://github.com/omacom/omarchy/releases/tag/v4.0.1).
