# Cuirass: Guix-native build coordinator

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Стан job definitions: **prototype; pinned API evaluation is part of `make check-guix-eval`**
- Стан інстансу: **NOT_RUN** — Cuirass/PostgreSQL host не підключений і jobs не реєструвалися
- Стан build/substitute: **NOT_RUN** — derivation evaluation does not build or publish anything

Файли: [specs](../ci/cuirass/specs.scm), [custom image job](../ci/cuirass/images.scm), [service fragment](../ci/cuirass/service.scm).

## Що саме доводить кожен рівень

| Рівень | Де перевіряється | Що він доводить |
| --- | --- | --- |
| Scheme API та service record | `make check-guix-eval` на Guix із `channels.lock.scm` | Модулі імпортуються, service створюється, custom job знижує ISO до derivation |
| Реальна збірка closure | Cuirass instance | Guix може зібрати derivation на worker |
| BIOS/UEFI boot | release workflow + QEMU | Носій завантажується у відповідному режимі |
| Запуск інсталятора й tool closure | release workflow + QEMU | Інсталятор стартує, його інструменти доступні в гості |
| Доступність substitutes | окремий `guix publish` deployment | Інші машини можуть завантажити дозволені store outputs |

Cuirass — не заміна QEMU. Зелений Cuirass job означає лише успішну побудову derivation; він не доводить, що ISO завантажується або що інсталятор працює.

Cuirass сам по собі **не публікує substitutes**. Для цього потрібен окремий `guix publish` service і окреме рішення щодо довіри, доступу й ліцензій. У WSM такої конфігурації зараз немає.

## Пінування та custom image job

Офіційний Guix у Cuirass specs прив'язаний до того самого commit, що й `channels.lock.scm`. Модуль job розташований у `ci/cuirass/images.scm` і має приватне ім'я `(ci cuirass images)`, яке відповідає шляху від кореня checkout.

Custom job використовує `arguments->systems` і `image->job` із `(gnu ci)` на зафіксованій ревізії Guix. Саме `image->job` створює образну derivation і вимикає grafting для build farm. `systems/live-minimal.scm` розв'язується з Guile load path checkout каналу, а не з робочого каталогу процесу.

`make check-guix-eval` додатково:
- завантажує `(ci cuirass images)` на exact Guix lock;
- завантажує service fragment і перевіряє, що він створює `cuirass-service-type` із `cuirass-configuration`;
- викликає custom job до отримання derivation, але **не запускає build**.

Цей source-tree evaluation не є автентифікацією WSM channel і не є реєстрацією Cuirass jobset.

## Межі довіри — не реєструвати до закриття

**Не виконуйте `cuirass register` для поточних specs, доки не закрито обидва gates:**

1. **Channel trust (#534 / Phase B).** WSM ще не має owner-signed introduction, `.guix-authorizations` і публічної keyring-гілки. Жодного `--disable-authentication`, вигаданого fingerprint або GitHub API commit як заміни підпису.
2. **Licensing (#367).** `systems/live-minimal.scm` включає пакет `wsm-tools`, отже і package job, і ISO job зачіпають його metadata та артефакти. Спершу потрібне окреме owner-рішення про ліцензію та redistribution.

До закриття gates specs лишаються інертним prototype. Не реєструйте їх навіть для «тимчасового» тесту з auth bypass. Після owner bootstrap потрібно також додати перевірену WSM introduction до channel input і повторити evaluation з зафіксованими input commits.

## Service fragment і мережа

`ci/cuirass/service.scm` — фрагмент для окремої Guix build-host системи, не частина WSM Desktop і не конфігурація цільового ПК. Він:
- імпортує pinned API з `(gnu services cuirass)`;
- додає specs у closure через `local-file`, а не неіснуючий шлях у `/run/current-system/profile`;
- залишає адміністративний UI на `localhost:8081`;
- не налаштовує `guix publish`, remote workers або substitute trust.

Для віддаленого адміністрування потрібен окремий автентифікований TLS reverse proxy; не відкривайте вбудований UI напряму в мережу.

## Як запускати після gates

Лише після owner-signed WSM channel trust, ліцензійного рішення #367 та перевірки input commits:
1. Розгорнути service fragment на окремому Guix host разом із PostgreSQL і guix-daemon.
2. Перевірити service closure та доступність UI тільки з loopback.
3. Зареєструвати specs зі стандартною перевіркою channel authentication.
4. Зафіксувати Cuirass evaluation ID, source commits, derivation paths та build logs.
5. Окремо порівняти результати з release workflow; QEMU acceptance лишається обов'язковим.
6. Публікацію substitutes розглядати як окремий deployment, а не як наслідок запуску Cuirass.

## Чесний стан

У поточному середовищі:
- pinned Guix evaluation запускається в GitHub Actions;
- Cuirass daemon, PostgreSQL, registration, evaluation IDs і real builds — **NOT_RUN**;
- BIOS/UEFI та installer acceptance залишаються за release/QEMU workflow.

Жоден документ або зелений unit test не змінює ці стани автоматично.