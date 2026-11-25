# WSM Installer — Qt 6 / QML preflight

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

**Стан:** перший GUI-прототип, лише читання / diagnostic-only. Це не інсталятор, який уже може розгортати систему.

## Що реалізовано

- Власне WSM Qt 6 / QML вікно з українським майстром: вступ → апаратні докази → read-only перелік дисків → параметри → підсумковий перегляд.
- Апаратний звіт береться через `python3 -m wsm_hwcheck`; той самий звіт передається у `python3 -m wsm_install --preflight --backend guix --dry-run`.
- Frontend показує фактичні поля report: виявлення, драйверне прив'язування, runtime firmware status, evidence та functional tests. Відсутні тести позначаються як такі, що не виконувалися.
- Перелік цілих дисків отримується окремим read-only викликом `lsblk --json --bytes --tree`. Вибір диска існує лише в пам'яті UI і не стає install target.
- Зв'язок із процесами зроблено через `QProcess::start(program, arguments)`: немає shell command string, eval або запуску довільного тексту з UI.
- Точні байти hardware report тимчасово зберігаються в приватному тимчасовому каталозі для існуючого validator/plan API. Каталог автоматично видаляється після завершення програми.
- Завершальна кнопка підтверджує лише перегляд. У цьому slice немає partition, format, mount, bootloader, `guix system init` або APPLY.

## Збірка для розробки

Потрібні Qt 6 development packages для Core, Gui, QML, Quick і Quick Controls, CMake 3.21+ та C++17:

```sh
cmake -S installer/gui -B build/wsm-installer -DCMAKE_BUILD_TYPE=Release -DWSM_BUILD_TESTS=ON
cmake --build build/wsm-installer
ctest --test-dir build/wsm-installer --output-on-failure
cmake --install build/wsm-installer --prefix /usr/local
```

У dev runtime PATH мають бути `python3`, `lsblk`, а активне Python-середовище має бачити пакети `wsm_hwcheck`, `wsm_install` і залежність `jsonschema[format]`. У Guix package `WSM_PYTHON_EXECUTABLE`, `WSM_GUIX_PYTHONPATH` (точний `site-packages` output `wsm-tools`) і `WSM_LSBLK_EXECUTABLE` прив’язуються до store paths; перевірка цього closure залишається обов’язковим exact-lock build.

## Межі інтеграції

Guix package definition міститься окремо у `wsm/packages/installer.scm`, щоб не конфліктувати з локальною роботою над live ISO у `systems/live.scm`, `scripts/build_iso.sh` та `wsm/packages/wsm.scm`. Його потрібно оцінити й зібрати на точному `channels.lock.scm`; саме додавання package expression не є доказом package closure.

Поточний `wsm_install` v0.1 завжди формує `diagnostic-only` plan або відмовляє з blocker-ами. UI не вигадує storage plan, freshness proof чи сумісність. Інтеграція в live image потребує окремого handoff до власника #170.

## Відомі межі

- Wizard navigation gates the parameter and review steps until the read-only disk inventory attempt has completed. An unavailable inventory is shown explicitly and permits only diagnostic review without a disk candidate.
- C++ behavioral tests cover navigation gates and a Python/Qt canonical JSON + SHA-256 golden vector.
- Поточний report schema v1 не доводить same-boot freshness. Frontend показує звіт як inventory snapshot, а не як підтвердження поточного boot session.
- `lsblk` дає read-only block-device inventory; це не тест здоров'я диска та не дозвіл його використовувати.
- Функціональні тести відображаються лише коли їх реально містить report. Collector не запускає тестування відео, мережі, звуку або сну.
- Цей прототип ще не проходив CMake/Qt compilation або Guix package build у середовищі, де доступний locked Guix. Не вважати його частиною перевіреного ISO, доки exact-lock package build, live launch та QML run-time smoke test не буде доведено.
