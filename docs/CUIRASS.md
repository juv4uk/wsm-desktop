# Cuirass: збірка всередині Guix

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **NOT_RUN** — конфігурацію виправлено, але Cuirass не зареєстровано й жоден job не запускався.
- Перевірка API: автоматизована оцінка модуля під pinned Guix має виконуватися у Guix workflow; вона не замінює справжній запуск Cuirass.
- Файли: [специфікації](../ci/cuirass/specs.scm), [custom job](../ci/cuirass/images.scm), [фрагмент сервісу](../ci/cuirass/service.scm).

## Роль Cuirass

Cuirass — Guix-native CI для збірки derivations з каналів Guix. У WSM це додатковий build/closure signal, не заміна GitHub Actions.

| Перевірка | Джерело доказу |
| --- | --- |
| Пакет wsm-tools будується з поточним каналом | Cuirass job після нормальної автентифікації |
| Мінімальний ISO derivation будується | Cuirass custom job після нормальної автентифікації |
| ISO реально завантажується у BIOS і UEFI | Лише QEMU acceptance workflow |
| Інсталятор реально стартує в guest | Лише QEMU acceptance workflow |
| Функції обладнання H170/GP107 працюють | Лише окремі native-hardware свідчення |

Cuirass не є релізним gate сам по собі. Зелений build не доводить boot, роботу інсталятора чи функціональність фізичного обладнання.

## Точність джерел

Guix у специфікаціях закріплено на commit з channels.lock.scm (4e5195be20d9b124df8a8bb69213412236e4668e). WSM channel натомість відстежує main. Це свідомий development/tracking lane, а не незмінний WSM source revision і **не є відтворенням релізу**. Релізний процес продовжує використовувати власний lock та exact source checkout.

Custom job використовує API саме pinned Guix:
- (gnu ci) — arguments->systems та image->job;
- (gnu system image) — iso9660-image та image-with-os;
- назва модуля (ci cuirass images) відповідає файлу ci/cuirass/images.scm;
- profile завантажується лише після знаходження systems/live-minimal.scm у %load-path канального checkout.

Це дозволяє уникнути розходження API з довільною системною версією Guix. Проте статична/модульна оцінка не доводить, що Cuirass реально завантажив модуль і побудував job; це все ще NOT_RUN.

## Автентифікація: Phase B ще не виконана

WSM channel поки не має owner-signed introduction, .guix-authorizations та public keyring branch. Тому специфікації **не можна реєструвати як робочі** до завершення owner-only Phase B і перевірки звичайною guix git authenticate.

- Не вимикати автентифікацію через --disable-authentication.
- Не вигадувати fingerprint, introduction commit, keyring чи підписи.
- Не вважати структурний validator доказом криптографічної довіри.
- Не додавати WSM channel до production release lock.

Після завершення Phase B власник може зареєструвати специфікації на окремому Cuirass host і перевірити нормальний authenticated checkout, появу обох jobs, реальну побудову package та ISO derivation. До того часу instance/job status лишається **NOT_RUN**.

## Substitutes та ліцензійні межі

Прапорець use-substitutes? дозволяє Cuirass використовувати доступні довірені substitutes для залежностей. Це **не публікація** власних WSM build products і не автоматичне надання доступу іншим машинам до локального store.

Публікація результатів потребує окремого guix publish/substitute-server deployment, ключів підпису, access policy та рішення власника. Її тут навмисно немає. Issue #367 — суперечність між package license metadata та repository LicenseRef-Volnist — не має owner-approved рішення; не роздавати WSM package substitutes і не вмикати публікацію до закриття цього питання.

## Запуск після Phase B

На окремому Guix host, після owner-approved trust bootstrap і перевірки, що WSM channel автентифікується звичайним способом:

    sudo -u postgres createdb cuirass

    guix shell cuirass postgresql -- \
      cuirass register --specifications=/run/current-system/profile/share/wsm/ci/cuirass/specs.scm \
                       --database="dbname=cuirass host=/var/run/postgresql" \
                       --interval=300

    guix shell cuirass -- \
      cuirass web --database="dbname=cuirass host=/var/run/postgresql"

До виконання цих кроків не називати Cuirass active, registered або green. Файл ci/cuirass/service.scm — фрагмент для хостової конфігурації; host має включати wsm-tools, щоб файл специфікацій був у system profile.

## Межі acceptance

Cuirass:
- будує derivations у Guix;
- не завантажує ISO у BIOS/UEFI;
- не запускає WSM_INSTALLER_OK у guest;
- не створює native H170/GP107 hardware evidence;
- не замінює release manifest, QEMU BIOS/UEFI acceptance чи перевірку походження артефактів.

Тому фінальний реліз лишається заблокованим власними релізними acceptance gates, навіть коли Cuirass у майбутньому стане зеленим.
