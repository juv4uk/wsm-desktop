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
| `(wsm systems performance)` | `wsm/systems/performance.scm` | існуючий модуль; потребує Guix evaluation у channel context |
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

### H170 Compatibility

- Лише явний opt-in, окремий lock і окрема збірка.
- NVIDIA 580.x для Pascal — кандидат, а не готовий пакет: потрібні exact source/package resolution, kernel ABI build, module signing/runtime binding та redistribution review.
- Compatibility не змінює Free closure і не може бути непомітною залежністю Free channel.

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

## Release gates

| Рівень | Що доводить | Чого не доводить |
|---|---|---|
| Channel metadata | Guix розпізнає структуру репозиторію | Authentication або package correctness |
| Authentication | Commit chain походить від authorized key | Scheme evaluation/build |
| Module evaluation | WSM Scheme modules імпортуються на pinned Guix | Package closure або runtime |
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
