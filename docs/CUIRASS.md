# Cuirass: збірка всередині Guix

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **NOT_RUN** — вихідний код частково перевірений; інстанс не запускався, реєстрації ще не було.
- Канонічна інтеграція: [#691](https://github.com/juv4uk/wsm-desktop/issues/691), виправлення API/шляхів: [#725](https://github.com/juv4uk/wsm-desktop/issues/725).
- Файли: [specs.scm](../ci/cuirass/specs.scm), [images.scm](../ci/cuirass/images.scm), [service.scm](../ci/cuirass/service.scm).

## Межі двох конвеєрів

Cuirass — Guix-native evaluator/build farm. Він не замінює GitHub Actions і не є дозволом на випуск.

| Доказ | Власник |
| --- | --- |
| Оцінювання та збірка derivations із зафіксованих каналів | Cuirass і pinned Guix evaluation |
| BIOS/UEFI boot, live-session та запуск інсталятора | GitHub Actions / QEMU |
| Підписане походження ISO й перевірка завантажених assets | Release workflow |
| Публічні trusted substitutes | Окрема конфігурація та рішення про ключі/доступ; зараз вимкнено |

Звичайна Cuirass service configuration сама по собі не публікує ISO й не створює публічний substitute endpoint. Не вмикайте guix publish, remote publish server або signing keys цим фрагментом.

## API зафіксованого Guix

WSM Free lock фіксує Guix commit 4e5195be20d9b124df8a8bb69213412236e4668e. Перевірка саме цього upstream source підтверджує:

- cuirass-service-type та cuirass-configuration експортуються модулем (gnu services cuirass);
- derivation->job експортується модулем (gnu ci);
- конфігурація цієї ревізії має поле fallback?, але не має use-substitutes?;
- custom-job модуль має відповідати шляху ci/cuirass/images.scm: (ci cuirass images);
- профіль systems/live-minimal.scm завантажується через primitive-load-path, щоб не залежати від поточного робочого каталогу.

Ці факти перевіряються source-evaluation harness-ом у tests/guix/source-module-evaluation.scm. Саме імпортування модулів ще не є доказом реєстрації jobset або успішної збірки.

## Trust gate: не реєструвати WSM завчасно

WSM канал наразі не має завершеного owner-signed Phase B bootstrap: .guix-authorizations, introduction commit і публічного keyring. Тому:

- не запускайте Cuirass registration/build для WSM channel, поки власник не завершить та не перевірить підписані артефакти;
- не використовуйте --disable-authentication, довільний fingerprint або непідписаний lock;
- локальне завантаження source tree може бути окремим development smoke, але його не можна називати споживанням автентифікованого WSM channel;
- Free jobset не повинен містити Nonguix, proprietary NVIDIA driver або nonfree firmware;
- Compatibility залишається окремим opt-in jobset із власним lock та legal/technical gates.

## Підготовка service host

Фрагмент ci/cuirass/service.scm використовує Guix local-file, а не неіснуючий шлях у системному профілі. Перед оцінюванням service configuration адміністратор має явно розмістити specs у root-owned конфігураційному каталозі:

```sh
sudo install -D -o root -g root -m 0644 \
  ci/cuirass/specs.scm \
  /etc/guix/wsm/ci/cuirass/specs.scm
```

Файл захоплюється в immutable Guix store під час оцінювання конфігурації. Після цього фрагмент можна включити до services окремого build host. Він слухає лише localhost на порту 8081, використовує штатний Guix daemon і PostgreSQL. Це фрагмент, а не повна система: повна декларація стала б другою правдою про host configuration.

Пакет Cuirass потрібно брати з того самого pinned Guix revision, а не з довільного рухомого каналу. У перевіреному commit пакетна декларація має Cuirass 1.3.7.

## Порядок першого запуску

Перший запуск — лише на disposable Guix System VM/host, після owner-signed channel Phase B та перевірки прав на store, PostgreSQL і worker. Початково — один local worker, без remote workers і без публікації substitutes.

Перед реальною реєстрацією:

1. guix describe -f channels має показувати точні authenticated revisions.
2. Перевірити jobset через cuirass register --check --specifications=ci/cuirass/specs.scm у середовищі з потрібними pinned modules.
3. Переконатися, що Cuirass працює з нормальною channel authentication і не обходить її.
4. Після явного допуску owner-а зареєструвати jobset із PostgreSQL та зберегти evaluation ID, build IDs, точні input commits і logs.
5. Довести фактичну збірку обох allowlisted targets: wsm-tools і Minimal Live image derivation.

Поки ці кроки не пройдені, всі Cuirass runtime/build результати мають статус **NOT_RUN**. Структурні тести або завантаження Scheme-модуля цього статусу не змінюють.

## Чого Cuirass не доводить

- **Не завантажує образ.** Зелений build означає, що derivation зібралася, а не що ISO стартує.
- **Не перевіряє інсталятор.** Маркер WSM_INSTALLER_OK та guest tool closure перевіряє QEMU workflow.
- **Не встановлює систему.** APPLY залишається вимкненим; фізичні диски не є тестовими цілями.
- **Не випускає RC.** Release gate, SLSA provenance, BIOS/UEFI acceptance і owner publication decision залишаються окремими.
