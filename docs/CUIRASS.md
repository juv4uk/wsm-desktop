# Cuirass: збірка всередині Guix

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **NOT_RUN** — конфігурація ще не зареєстрована; Cuirass instance та жоден Cuirass job не запускалися.
- Перевірка в CI: pinned Guix оцінює custom job до ISO derivation і будує сервісний об'єкт; це не запуск Cuirass scheduler і не побудова ISO.
- Файли: [специфікації](../ci/cuirass/specs.scm), [image job](../ci/cuirass/images.scm), [фрагмент сервісу](../ci/cuirass/service.scm).

## Навіщо Cuirass

Cuirass — Guix-native CI, який обчислює й збирає derivations зі специфікацій каналів. Він доповнює GitHub Actions, але не замінює релізне приймання.

| Що доводимо | Джерело доказу |
| --- | --- |
| wsm-tools та Minimal Live ISO derivation обчислюються під pinned Guix | pinned Guix profile-evaluation workflow |
| Cuirass scheduler зареєстрував jobset і будує derivations | окремий реальний Cuirass instance/job run |
| ISO завантажується в BIOS і UEFI | QEMU acceptance у release workflow |
| Інсталятор стартує в завантаженому гості, а його інструменти доступні | serial/tool-closure докази з QEMU guest |
| Фізичні можливості H170/GP107 працюють | окремі native-hardware свідчення |

Зелена Guix evaluation не означає, що Cuirass instance працює, а зелений Cuirass build не доводить boot, роботу інсталятора чи функціональність фізичного обладнання.

## Точність каналів і відтворюваність

- Офіційний Guix у специфікаціях закріплений на commit 4e5195be20d9b124df8a8bb69213412236e4668e, який використано у channels.lock.scm.
- WSM channel у цих development specs відстежує main. Його commit змінюється між evaluations, тому це **не незмінний WSM source pin** і **не відтворення релізної пари каналів**.
- Для кожного реального Cuirass evaluation зберігайте фактичні resolved commits Guix і WSM. Release manifest має окремо фіксувати точні commits, що побудували конкретний артефакт.

Custom job у ci/cuirass/images.scm відповідає pinned Guix API:
- (gnu ci) надає arguments->systems та image->job;
- (gnu system image) надає image-with-os та iso9660-image;
- (ci cuirass images) відповідає розташуванню ci/cuirass/images.scm;
- systems/live-minimal.scm знаходиться в %load-path перевіреного WSM channel checkout;
- job обмежено x86_64-linux, архітектурою першого WSM release target.

image->job створює job metadata і lower-ить image до derivation через store. Guix smoke перевіряє появу очікуваного derivation, але не запускає саму побудову ISO. Не називайте цю перевірку build PASS.

## Автентифікація: WSM Phase B — prerequisite

**Не реєструйте production Cuirass jobset проти WSM channel, доки owner-controlled Phase B не завершено.** Потрібні .guix-authorizations, signed introduction/history та публічна keyring-гілка. Після цього звичайний guix git authenticate має успішно перевірити WSM channel.

- Не вимикати автентифікацію через --disable-authentication.
- Не створювати або не вгадувати fingerprint, introduction commit, keyring чи підпис.
- Не вважати структурні validators доказом криптографічної довіри.
- Не включати неавтентифікований WSM channel у production release lock.

Після завершення Phase B власник може окремо зареєструвати specs на build host, пересвідчитися в authenticated checkout, збереженні resolved commits, появі обох jobs та реальній збірці package й image derivations. До цього моменту реальний Cuirass instance/job status залишається **NOT_RUN**.

## Сервіс, доступ і substitutes

ci/cuirass/service.scm — фрагмент для окремого Guix build host, а не повна система WSM. Він:
- імпортує сервіс із (gnu services cuirass) — саме цей модуль містить pinned cuirass-service-type;
- передає специфікацію через local-file "specs.scm", тому не залежить від неіснуючого /run/current-system/profile/share/... шляху;
- прив'язує вебінтерфейс до localhost:8081;
- використовує дійсне поле fallback?; у pinned cuirass-configuration **немає** поля use-substitutes?.

Поведінка substitute lookup визначається конфігурацією Guix daemon і дозволеними довіреними серверами. Локальний Cuirass scheduler сам по собі **не публікує** власні результати для інших машин. Для розповсюдження build outputs потрібна окрема архітектура Cuirass remote server/workers або незалежного substitute server, ключі підпису, client trust, мережеві ACL та політика доступу.

Публікацію WSM outputs тут навмисно не налаштовано. Issue #367 містить невирішену суперечність щодо ліцензування wsm-tools (метадані пакета GPL-3+ проти LicenseRef-Volnist у репозиторії). Не запускати guix publish, не роздавати WSM substitutes і не створювати signing keys до owner-approved ліцензійного й операційного рішення.

Адміністративний вебінтерфейс залишати на loopback. Віддалений доступ, коли він буде потрібен, потребує окремого автентифікованого reverse proxy і контрольованої мережевої політики.

## Запуск після Phase B

Лише на окремому Guix host після завершення owner-signed trust bootstrap і перевірки звичайної authentication:

    sudo -u postgres createdb cuirass

    guix shell cuirass postgresql -- \
      cuirass register --specifications=ci/cuirass/specs.scm \
                       --database="dbname=cuirass host=/var/run/postgresql" \
                       --interval=300

    guix shell cuirass -- \
      cuirass web --database="dbname=cuirass host=/var/run/postgresql" \
                  --port=8081 --listen=localhost

Не вважати ці команди виконаними: у поточному стані це інструкція для owner-controlled host bootstrap, не runtime evidence.

## Межі acceptance

Cuirass:
- обчислює та будує Guix derivations, коли instance справді працює;
- не завантажує ISO в BIOS/UEFI;
- не запускає WSM_INSTALLER_OK у QEMU guest;
- не створює native H170/GP107 hardware evidence;
- не замінює release manifest, QEMU BIOS/UEFI acceptance та перевірку походження артефактів.

**Поточний стан: NOT_RUN** для реєстрації/побудови Cuirass, ISO build у Cuirass, QEMU BIOS/UEFI та фізичного H170/GP107. Ці статуси змінюються тільки після отримання відповідних logs і артефактів, а не після проходження текстових тестів.
