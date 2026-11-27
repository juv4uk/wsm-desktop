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
| `(wsm systems performance)` | `wsm/systems/performance.scm` | source-tree evaluation проти pinned Guix додається у CI; authenticated channel lookup — тільки після Phase B |
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

#### Nouveau + nonfree GP107 firmware

Цей варіант зберігає відкритий kernel/userspace stack Nouveau + Mesa/NVK, але явно додає потрібні NVIDIA GP107 firmware blobs із linux-firmware. Це не Free-профіль: для GP107 GR 3D/compute потрібні FECS/GPCCS та пов'язаний набір firmware, який має окремі vendor license terms.

- Не переносити nonfree firmware до H170 Free.
- Linux-libre Free profile не є автоматично придатною основою для цього варіанту; потрібно окремо вибрати й перевірити kernel package/configuration, який може завантажувати зовнішні firmware.
- Перевірити exact GP107 file set, WHENCE entries, усі symlink targets, SHA-256, provenance, license files, redistributability, package closure та presence в live rootfs, initrd й installed rootfs.
- Не додавати весь linux-firmware набором «на всяк випадок». Власний subset допустимий лише після доказу повного dependency set і ліцензійної повноти.
- Не вважати успішний Kali/NVK compute witness доказом роботи цього Guix Compatibility closure.

#### Proprietary NVIDIA 580.x

Це інший, взаємовиключний boot path: proprietary NVIDIA kernel modules/userspace для Pascal та їхній власний firmware stack.

- NVIDIA 580.x — кандидатна гілка для Pascal, не release-ready package.
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

Bootstrap має бути виконаний власником ключа:

1. Вибрати/підтвердити OpenPGP signing key і перевірити його повний fingerprint локально. Приватний ключ ніколи не передавати в репозиторій або чат.
2. Створити `.guix-authorizations` із цим fingerprint.
3. Додати експортований **публічний** ключ як `.key` до окремої orphan-гілки `keyring`.
4. Зробити підписаний OpenPGP Git commit, який уперше додає `.guix-authorizations`; саме він стає introduction commit.
5. Перевірити історію командою `guix git authenticate <commit> <fingerprint>`, потім виконати реальний `guix time-machine` із WSM channel та звичайною authentication.
6. Опублікувати introduction commit і fingerprint у цьому документі та в release notes.

Після introduction кожен commit у каналі має бути підписаний авторизованим ключем. Не використовувати непідписані GitHub-generated merge commits у захищеній історії; узгодити signed fast-forward/rebase workflow та правила GitHub перед вмиканням channel release. Не використовувати `--disable-authentication` для acceptance.

## Що перевіряє CI до trust bootstrap

До появи owner-signed introduction CI може перевіряти сумісність WSM Scheme source tree з API pinned Guix. Smoke-test імпортує `(wsm systems performance)` через локальний load-path `-L .` і перевіряє, що експортований набір служб не порожній. Його результат позначається `WSM-SOURCE-MODULE-EVAL-OK`.

Це **source-tree module evaluation**, а не завантаження WSM із Guix channel: локальний checkout додається до module load path. Цей тест не доводить channel lookup, authentication, package closure або runtime. CI явно виводить `WSM_CHANNEL_AUTHENTICATION=NOT_TESTED`.

Після Phase B потрібна окрема перевірка реального channel consumer: owner-approved WSM commit у двоканальному H170 lock, стандартний `guix time-machine` **без** `-L .` і без `--disable-authentication`, після чого імпорт того самого public module. Не вмикати цей gate до підписаного introduction та підтвердженого authorization chain.

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

Поточний `wsm-tools` package definition має невідповідність metadata до repo license; це відстежує #367. До вирішення не публікувати його як release-ready channel package і не маскувати проблему заміною ліцензійного ідентифікатора. Кожен майбутній пакет має мати коректний origin, hash, build system, inputs і фактичну license metadata.

## Джерела

- [GNU Guix Reference Manual — Channels](https://guix.gnu.org/manual/en/html_node/Channels.html)
- [Channel Authentication](https://guix.gnu.org/manual/en/html_node/Channel-Authentication.html)
- [Specifying Channel Authorizations](https://guix.gnu.org/manual/en/html_node/Specifying-Channel-Authorizations.html)
- [Invoking guix git authenticate](https://guix.gnu.org/manual/en/html_node/Invoking-guix-git-authenticate.html)
