# Канал GNU Guix WSM

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Канонічне завдання: [#534](https://github.com/juv4uk/wsm-desktop/issues/534).
- Перший hardware target: [H170 firmware matrix](hardware/H170-FIRMWARE-MATRIX.md), [Free manifest](../drivers/profiles/h170-free.json), [Compatibility manifest](../drivers/profiles/h170-compatibility.json).
- Стан документа: channel skeleton; криптографічний trust bootstrap ще не виконано.

## Призначення

`juv4uk/wsm-desktop` є джерелом WSM-owned Guix-модулів. Це звичайний GNU Guix channel, а не форк Guix і не другий package manager. Upstream-пакети залишаються в офіційному Guix/Nonguix; WSM додає лише власні інтеграції, сервіси, package definitions та профілі, для яких є конкретна потреба.

Кореневий [`.guix-channel`](../.guix-channel) оголошує формат метаданих каналу v0 і його canonical URL. Модулі вже мають правильний кореневий namespace:

| Scheme module | Файл | Стан |
|---|---|---|
| `(wsm systems performance)` | `wsm/systems/performance.scm` | source-tree evaluation на pinned Guix; authenticated channel lookup потребує окремого Phase B bootstrap |
| `(wsm packages wsm)` | `wsm/packages/wsm.scm` | package metadata має невирішену ліцензійну суперечність #367; не оголошувати release-ready |

Не переносити модулі з `wsm/` без необхідності: цей шлях уже відповідає Scheme namespace `(wsm …)`. Файли `systems/*.scm` залишаються machine/release configurations, а не публічним API channel namespace.

## Перший реліз: тільки H170

Release target — одна конкретна платформа власника:

- Gigabyte GA-H170-Gaming 3, BIOS F22e;
- Intel Core i5-6400 (Skylake);
- Intel HD Graphics 530 (i915);
- NVIDIA GeForce GTX 1050 Ti, GP107, PCI ID `10de:1c82`;
- інші компоненти — лише ті, що підтверджені hardware inventory та manifests.

Канонічні факти пристроїв і рівні доказів зберігаються в JSON manifests. Не створювати другу, розбіжну копію цих фактів у Scheme.

### H170 Free

- Офіційний Guix channel lock, Linux-libre та upstream Mesa.
- Немає Nonguix, proprietary driver або nonfree firmware у default closure.
- Для GP107 не заявляти Free 3D/compute без потрібної NVIDIA FECS/GPCCS firmware; базовий display/KMS перевіряти окремо.
- Для Intel HD 530 відокремлювати базовий i915 graphics від DMC-backed runtime power management та інших optional capabilities.
- CPU microcode, firmware і кожна периферійна функція мають окремий evidence state.

### H170 Compatibility — лише явний opt-in

Compatibility — це окрема родина профілів, а не один змішаний набір драйверів. Кожен варіант має власний system definition, closure, release evidence та чітко визначений активний GPU driver. У межах одного boot profile не завантажувати Nouveau і proprietary NVIDIA kernel driver одночасно.

#### Nouveau + GP107 firmware — RESEARCH ONLY / NOT SHIPPABLE

Цей технічний варіант описує відкритий kernel/userspace stack Nouveau + Mesa/NVK із зовнішньою GP107 firmware. Він залишається **дослідницьким кандидатом**, а не дозволеним WSM Compatibility package/profile. GP107 docs/39 — source-only карта FECS/GPCCS, ACR, SEC2 та NVDEC paths; вона не доводить boot request/load, точний runtime file set або Guix closure.

LICENCE.nvidia §2.1.2 містить умову щодо використання firmware на ОС, що розповсюджуються під OSI-approved open-source license, незмінених binaries та копії ліцензії. Саме opt-in позначення Compatibility не підтверджує виконання цієї умови; WSM LicenseRef-Volnist і #367 потребують окремого owner/legal рішення. Згідно з прийнятим release gate #586, до письмового clearance для конкретної distribution model **WSM не включає й не перерозповсюджує NVIDIA GP107 firmware ані в Free, ані в Compatibility channel/ISO**.

- Не додавати firmware blobs, subset packages, downloader, package assets або копії до репозиторію чи release.
- Не заявляти цей варіант як доступний для встановлення, build-ready чи shippable.
- Не трактувати сторонній Kali/NVK compute witness як доказ package closure, firmware provenance, Guix runtime або H170 acceptance.
- Повернутися до оцінки розповсюдження лише після письмового clearance для конкретної ОС/ліцензійної моделі та окремих closure/runtime acceptance gates.

#### Proprietary NVIDIA 580.x

Це інший, взаємовиключний boot path: proprietary NVIDIA kernel modules/userspace для Pascal та їхній власний firmware stack.

- NVIDIA 580.x — лише окремий дослідницький кандидат для Pascal, не package для WSM channel/ISO і не release-ready. Будь-яке використання/розповсюдження потребує окремого owner/legal clearance за EULA та перевірки всіх модифікацій package recipe.
- У pinned Nonguix recipe nvidia-firmware-580 є GSP firmware для proprietary NVIDIA driver; це **не** Nouveau FECS/GPCCS firmware. Для Nouveau потрібен окремий linux-firmware path.
- Потрібні точна версія/source archive, kernel ABI build, module signing/runtime binding, userspace closure, firmware provenance й redistribution review.
- Перевіряти також ELF patching/relocation у package recipe проти умов NVIDIA EULA; не публікувати відповідні binary artifacts, доки ліцензійний review не завершено.

Обидва Compatibility paths є дослідницькими кандидатами. Їх не можна вважати готовими лише через наявність recipe, firmware package або драйверного модуля в ISO. Package resolution, build, closure, initrd/rootfs presence, runtime binding та функціональні тести залишаються окремими acceptance gates.

Compatibility не змінює H170 Free closure і не може бути непомітною залежністю Free channel.

Wi-Fi, Bluetooth, Thunderbolt, webcam та інша неінвентаризована периферія залишаються `unknown/not-assessed`. Не обіцяти універсальну підтримку ПК у першому релізі.

## Pinning і використання

Поточний `channels.lock.scm` навмисно залишається lock-файлом офіційного Guix для наявних Free acceptance gates. Не додавати до нього WSM channel непомітно: це змінить чинний contract і checker.

Після trust bootstrap для релізу буде опубліковано окремі lock-файли, які pin-ять **обидва** джерела — Guix та WSM — на точні commit SHA. Compatibility lock додатково pin-ить Nonguix. Жоден release lock не використовуватиме рухому `main` як невизначений input.

Шаблон запису WSM у користувацькому `channels.scm` (значення в кутових дужках — навмисні placeholders; це не готовий конфіг):

```scheme
(channel
 (name 'wsm)
 (url "https://github.com/juv4uk/wsm-desktop.git")
 (commit "<WSM_CHANNEL_COMMIT>")
 (introduction
  (make-channel-introduction
   "<SIGNED_INTRODUCTION_COMMIT>"
   (openpgp-fingerprint "<OWNER_OPENPGP_FINGERPRINT>"))))
```

Не копіювати introduction із неперевіреного повідомлення. Точний commit і fingerprint будуть опубліковані разом із перевіреним trust bootstrap.

## Автентифікація каналу — ще не налаштована

Наявність `.guix-channel` сама по собі **не** робить канал authenticated. У репозиторії ще немає підтвердженого WSM `.guix-authorizations`, signed introduction commit і публічного keyring branch. Тому зараз не можна рекламувати WSM channel як криптографічно автентифікований або включати його до production release lock.

Bootstrap має бути виконаний власником ключа. Нижче — точний формат і порядок локальної операції; placeholders не можна копіювати як готові значення.

1. Перевірити локальні secret keys та повний fingerprint, включно з signing subkey:
   ```sh
   gpg --list-secret-keys --keyid-format=long --with-subkey-fingerprint
   ```
   Вибрати ключ, яким реально підписуватиметься introduction commit. Перевірити його повний fingerprint локально; короткий key ID не підходить.
2. Створити `.guix-authorizations` у форматі Guix. Для одного owner key структура така:
   ```scheme
   (authorizations
    (version 0)
    (("FULL OPENPGP FINGERPRINT WITH SPACES"
      (name "WSM channel owner"))))
   ```
   Замінити placeholder на повний fingerprint ключа з попереднього кроку. Це публічна інформація; приватний ключ ніколи не передавати в репозиторій або чат.
3. Експортувати **лише публічний** ключ у файл із розширенням `.key`. Перевірити fingerprint:
   ```sh
   FPR='FULL OPENPGP FINGERPRINT WITH SPACES'
   KEY_NAME="$(printf '%s' "$FPR" | tr -d ' ')"
   gpg --armor --export "$FPR" > "/tmp/$KEY_NAME.key"
   gpg --show-keys --with-fingerprint "/tmp/$KEY_NAME.key"
   ```
4. Додати цей `.key` до окремої orphan-гілки `keyring` (рекомендовано саме orphan branch), запушити її та перевірити, що GitHub містить лише публічні ключі у `.key`-файлах. Не додавати приватні keyring exports, GPG home, revocation certificates або інші секрети.
5. Повернутися до авторитетної WSM гілки, перевірити чистий worktree і створити **підписаний** commit, який уперше додає `.guix-authorizations`:
   ```sh
   git status --short
   git add .guix-authorizations
   git -c user.signingkey="$FPR" commit -S -m "security(guix): introduce channel authorizations"
   INTRO="$(git rev-parse HEAD)"
   ```
   Не використовувати GitHub web editor, REST contents API або непідписаний PR merge для introduction commit: вони не виконують owner-local OpenPGP signing.
6. Перевірити локальну історію та keyring:
   ```sh
   git log -1 --show-signature --format=fuller "$INTRO"
   guix git authenticate "$INTRO" "$FPR"
   ```
   Переконатися, що команда завершилася з exit code 0 без `--disable-authentication`, і перевірити звичайний `guix time-machine` consumer на окремому тимчасовому channels file.
7. Лише після успішної перевірки опублікувати introduction commit і fingerprint у цьому документі та release notes, а точний WSM commit внести в окремі release locks.

**Критична властивість історії:** кожен commit після introduction має бути підписаний ключем, дозволеним у `.guix-authorizations` його батьківського commit. Merge commit має бути підписаний ключем, дозволеним в обох батьківських гілках. Тому до Phase B слід узгодити signed fast-forward/rebase workflow; звичайний GitHub-generated merge commit не можна автоматично вважати authenticated. Не вмикати branch protection / required authentication, доки owner не перевірив повний шлях на тестовій гілці.

Після introduction кожен commit у каналі має бути підписаний авторизованим ключем. Не використовувати непідписані GitHub-generated merge commits у захищеній історії; узгодити signed fast-forward/rebase workflow та правила GitHub перед вмиканням channel release. Не використовувати `--disable-authentication` для acceptance.

## Що перевіряє CI до trust bootstrap

До появи owner-signed introduction CI може перевіряти Scheme API/evaluation сумісність WSM source tree з pinned Guix. Поточний smoke-test використовує `-L .`, тому module lookup іде з checkout репозиторію. Його успіх позначається тільки як `WSM-SOURCE-MODULE-EVAL-OK`; це **не** channel import і не authentication.

Після Phase B потрібна окрема перевірка реального channel consumer: зафіксувати owner-approved WSM commit у H170 release lock, запустити стандартний `guix time-machine` без `-L .` і без `--disable-authentication`, а тоді імпортувати той самий public module. Цей тест не можна вмикати раніше підписаного introduction та підтвердженої authorizations chain.

### Діагностичний CLI smoke до Phase B

`make check-guix-eval` запускає `scripts/check-wsm-channel-set.sh` на
фактичному `channels/wsm.scm` через Guix CLI:

- звичайний `guix time-machine -C channels/wsm.scm -- describe -f channels`
  має відмовити саме через відсутній owner-signed WSM introduction або
  authorization; network, parse чи branch error не зараховується;
- окремий виклик із `--disable-authentication` використовується лише для
  діагностики та перевіряє, що набір містить `guix` і `wsm`;
- результат явно лишається `WSM_CHANNEL_AUTHENTICATION=NOT_TESTED`.

Цей smoke не автентифікує канал, не створює Phase B artifacts і не дозволяє
додавати WSM до production/release locks. Він лише тестує межу відмови до
виконання owner-local bootstrap.

## Release gates

| Рівень | Що доводить | Чого не доводить |
|---|---|---|
| Channel metadata | Guix розпізнає структуру репозиторію | Authentication або package correctness |
| Authentication | Commit chain походить від authorized key | Scheme evaluation/build |
| Source-tree module evaluation (CI) | WSM Scheme module imports/evaluation сумісні з pinned Guix API під час завантаження з checkout (`-L .`) | Завантаження WSM як channel, authentication, closure або runtime |
| Authenticated channel consumer test | Після owner-signed bootstrap `guix time-machine` завантажує точний WSM commit без локального `-L .` | Package/system build або hardware runtime |
| Package/system build | Derivations і closure збираються | Boot або фізичне обладнання |
| QEMU boot | Загальний boot path у VM | Фізичну H170/GPU функціональність |
| H170 functional test | Точна функція перевірена на цільовому ПК | Інші пристрої/конфігурації |

Для кожного gate зберігати commit SHA, Guix revision, команду, exit code та артефакти. `unknown` ніколи не перетворюється на `pass` лише через успішний build.

## Ліцензійна межа

Поточний `wsm-tools` package definition має невідповідність metadata до repo license; це відстежує #367. До вирішення не публікувати його як release-ready channel package і не маскувати проблему заміною ліцензійного ідентифікатора. Окремо, merged policy #586 забороняє включення або redistribution NVIDIA GP107 firmware у Free чи Compatibility channel/ISO до письмового owner/legal clearance для exact distribution model. Кожен майбутній пакет має мати коректний origin, hash, build system, inputs і фактичну license metadata.

## Джерела

- [GNU Guix Reference Manual — Channels](https://guix.gnu.org/manual/en/html_node/Channels.html)
- [Channel Authentication](https://guix.gnu.org/manual/en/html_node/Channel-Authentication.html)
- [Specifying Channel Authorizations](https://guix.gnu.org/manual/en/html_node/Specifying-Channel-Authorizations.html)
- [Invoking guix git authenticate](https://guix.gnu.org/manual/en/html_node/Invoking-guix-git-authenticate.html)
