# Cuirass: відтворювана збірка всередині Guix

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **конфігурація присутня; pinned-Guix evaluation очікує CI; інстанс не запускався**
- Файли: [специфікації](../ci/cuirass/specs.scm), [custom job](../ci/cuirass/images.scm), [сервіс](../ci/cuirass/service.scm)

## Навіщо Cuirass поруч із GitHub Actions

Cuirass — Guix-native build automation. Він реєструє jobs, будує derivations через Guix daemon і зберігає результати та історію в store/базі. GitHub Actions лишається окремим рівнем приймання образу й інсталятора.

| Що доводимо | Де |
| --- | --- |
| Scheme-модулі, service API і profile evaluation на pinned Guix | Guix CI workflow |
| Derivation live image на однакових Guix та WSM revisions | Cuirass і Guix CI |
| Завантаження ISO у BIOS/UEFI через QEMU | release workflow |
| Реальний запуск інсталятора в гості | release workflow |
| Власні substitutes для інших машин | **не налаштовано** |

Cuirass не публікує власні результати як substitutes лише через те, що він виконує збірки. У локальному режимі результати зберігаються у store та базі; довірені substitutes можуть використовуватися через конфігурацію Guix daemon. Публікація build outputs іншим машинам потребує окремої remote-server/worker топології, `guix-publish`, підписних ключів і конфігурації клієнтського trust. Не видавати локальну історію збірок за substitute service.

## Вхідні канали та межа довіри

Офіційний Guix channel у специфікаціях закріплений за commit із `channels.lock.scm` та має відому channel introduction. WSM channel наразі вказує на рухомий `main`. Це development input, не owner-authenticated release lock.

Поки власник не завершив підписаний bootstrap WSM channel (introduction/authorizations) і не зафіксував точний release commit, Cuirass job не є доказом довіреної release-збірки WSM. Не обходити цей gate через `--disable-authentication`. Поточний Scheme evaluation локально завантажує вихідний код для перевірки Guix API; він **не** тестує автентифікацію віддаленого WSM channel.

## Дві дороги до одного профілю

`ci/cuirass/images.scm` створює job для `systems/live-minimal.scm`. Для порівняння саме тих самих derivations мають збігатися точні Guix і WSM source revisions. Оскільки WSM channel зараз стежить за `main`, Cuirass evaluation може описувати інший commit, ніж майбутній релізний lock. Зберігати фактично resolved commit кожної evaluation.

Cuirass custom job використовує модуль `(ci cuirass images)`, що відповідає шляху `ci/cuirass/images.scm`. Він створює той самий тип `iso9660` образу, що й release workflow, через штатний Guix helper `image->job`, `image` record і `iso9660-image`; helper передає derivation у Cuirass із `#:job-type . image`. `derivation->job` надходить із `(gnu ci)`, `%graft?` — із `(guix packages)`, а `assq-ref` — із `(srfi srfi-1)`. Pinned Guix evaluation викликає `cuirass-jobs`, опускає image derivation до store job record і перевіряє його ім'я та derivation path; це не збирає ISO payload.

## Запуск Cuirass вручну

Це інструкція для окремого Guix build host із PostgreSQL. Вона не означає, що інстанс уже було запущено:

```sh
sudo -u postgres createdb cuirass

guix shell cuirass postgresql -- \
  cuirass register --specifications=ci/cuirass/specs.scm \
                   --database="dbname=cuirass host=/var/run/postgresql" \
                   --interval=300

guix shell cuirass -- cuirass web \
  --database="dbname=cuirass host=/var/run/postgresql" \
  --port=8081 --listen=localhost
```

Вебінтерфейс доступний на `http://localhost:8081`. Сам Cuirass web UI не надає автентифікації: не відкривати його в публічну мережу. Для віддаленого доступу потрібні автентифікований reverse proxy та TLS.

Для декларативного запуску використовується фрагмент [`service.scm`](../ci/cuirass/service.scm). Його треба завантажити з вихідного checkout, щоб `local-file "specs.scm"` міг відносно цього Scheme-файлу захопити сусідню специфікацію в store. Фрагмент визначає `wsm-cuirass-service`, який додається до `services` хост-системи; це не окрема повна конфігурація машини.

## Межі доказів

- **Не завантажує образ.** Сам факт успішного Cuirass build не означає, що ISO стартує в BIOS/UEFI.
- **Не перевіряє інсталятор.** Cuirass не запускає інтерактивний або автоматизований інсталятор у QEMU.
- **Не доводить boot.** Зелений Cuirass job означає, що derivation будується, а не те, що ISO стартує в BIOS/UEFI.
- **Не доводить інсталяцію.** Cuirass не запускає інтерактивний або автоматизований інсталятор у QEMU.
- **Не доводить WSM channel authentication.** Для цього потрібен окремий owner-signed bootstrap і перевірка exact release lock.
- **Не доводить фізичну сумісність H170/GTX 1050 Ti.** Для неї потрібні окремі owner-approved hardware evidence.

Поточний Guix CI перевіряє імпорт job-модуля, його критичні binding-и та створення сервісного об'єкта проти pinned Guix API. **Інстанс не запускався**: локальні build-host і PostgreSQL не були доступні під час цього аудиту.