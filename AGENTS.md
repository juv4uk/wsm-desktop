<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

# Інструкції для агентів WSM Desktop

Це точка входу для автоматизованих агентів і людей, які працюють у репозиторії. Цей файл не створює паралельного набору правил: канонічні політики залишаються у відповідних документах та acceptance-контрактах.

## Карта джерел

- [CONTRIBUTING.md](CONTRIBUTING.md) — внесок, тестування, exact-head CI, merge policy та мовна політика.
- [LESSONS-FROM-OMARCHY.md](docs/LESSONS-FROM-OMARCHY.md) — перевірені failure modes із Omarchy та WSM-запобіжники.
- [docs/REVIEW-2026-11-26.md](docs/REVIEW-2026-11-26.md) — зовнішній огляд стану репозиторію; історичний зріз, не контракт.
- [docs/ECOSYSTEM-PRINCIPLES.md](docs/ECOSYSTEM-PRINCIPLES.md) — критерії когерентності екосистеми: стек, evidence per claim, `fail safely`, антипатерни, Definition of Done.
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — середовище розробки та Guix bring-up.
- [agents/skills/](agents/skills/) — task-specific процедури; для installer/provisioning читайте [installer-lifecycle.md](agents/skills/installer-lifecycle.md).
- [docs/](docs/) — архітектура та прийняті рішення. Зокрема [STATELESS-CONFIGURATION.md](docs/STATELESS-CONFIGURATION.md), [PARTITIONING.md](docs/PARTITIONING.md) і [INSTALLER-HANDOFF.md](docs/INSTALLER-HANDOFF.md) є власниками своїх контрактів.
- [schemas/](schemas/) і відповідні validators — машинно-читані контракти. Не змінюйте їхню версійну семантику мовчки.

Не підтримуйте другу копію списку команд, профілів, станів або acceptance-вимог. Інші документи мають посилатися на канонічного власника.

Новий документ без посилання з документа-власника не потрапить у `main`: `check-doc-ownership` вимагає, щоб кожен документ був досяжний від точки входу, кожен ADR — зареєстрований у `docs/DECISIONS.md`, а кожен переклад — прив'язаний до канонічного оригіналу.

## Який інструмент для якої роботи

Це маршрут, а не друга копія процедур: для кожної роботи названо канонічного власника, а команда наведена лише як вхід у нього. Кожна команда нижче існує в репозиторії; у дужках — файл, який її визначає.

### 1. Підготовка релізу

- Збірку запускає коміт у `main`, що змінює [RELEASE-REQUEST.txt](RELEASE-REQUEST.txt): рівно один непорожній рядок без `#` із tag форми `0.1.0-rcN-minimal-live`, решта — коментарі. Це тригер `.github/workflows/release-minimal-live.yml`.
- Перед пушем: `make check` (ціль `check` у [Makefile](Makefile); вимога — розділ «Перевірки» у [CONTRIBUTING.md](CONTRIBUTING.md)).
- Чернетку перевіряють read-back-ом завантажених assets: `python3 scripts/verify_release_assets.py --expected-dir DIR --downloaded-dir DIR` (`scripts/verify_release_assets.py`); походження — `gh attestation verify` (розділ «Криптографічне походження артефактів» у [docs/RELEASE-MINIMAL-LIVE.md](docs/RELEASE-MINIMAL-LIVE.md)).
- Пуш створює лише чернетку. Публікація — окремий ручний запуск того ж workflow із входом `publish_prerelease`, тобто рішення власника. Деталі: [docs/RELEASE-MINIMAL-LIVE.md](docs/RELEASE-MINIMAL-LIVE.md), [ISO-RELEASE.md](ISO-RELEASE.md).

### 2. Робота з каналом Guix

- Стан каналу звітує `python3 scripts/check_channel_auth.py .` (`scripts/check_channel_auth.py`; та сама команда в цілі `check-channel-artifacts`). Він друкує, які артефакти присутні, і навмисно не вирішує, чи канал автентифікований.
- Заблоковано на підписі власника: `.guix-authorizations`, підписаний introduction commit і keyring-гілка. Без них канал не можна називати authenticated чи вносити в release lock; агент не вигадує fingerprint, commit або ключ. Порядок кроків, включно з `guix git authenticate`, — [docs/GUIX-CHANNEL.md](docs/GUIX-CHANNEL.md), розділ «Автентифікація каналу».
- H170 Free package candidates: `drivers/profiles/h170-free-packages.scm`; exact-lock build evidence runs via `.github/workflows/hw-build-evidence.yml`. This is an upstream-only candidate closure, not a hardware support verdict or permission to export NARs/releases/substitutes.

### 3. Перший hardware profile для машини власника (Gigabyte GA-H170-Gaming 3)

Порядок обов'язковий: каталог профілю не створюють, доки немає звіту `wsm-hwcheck` з native Linux.

1. Завантажити саму машину в native Linux (не Windows/WSL) і зібрати read-only звіт: `python3 -m wsm_hwcheck --output ./hwcheck-report.json` ([docs/hardware/HWCHECK.md](docs/hardware/HWCHECK.md)).
2. Лише після цього створити `profiles/hardware/gigabyte/ga-h170-gaming3/` з `profile.scm` на основі `profiles/hardware/template.scm`.
3. `python3 scripts/draft_profile_evidence.py --report hwcheck-report.json --vendor GIGABYTE --model "GA-H170-Gaming 3" --slug gigabyte/ga-h170-gaming3 --out profiles/hardware/gigabyte/ga-h170-gaming3/evidence.json` (`scripts/draft_profile_evidence.py`). Генератор не створює `profile.scm`, не ставить `pass` і не перезаписує наявні файли.
4. Додати functional-test logs у `artifacts/` і заповнити `verified_functions`, `known_limitations` та непорожній `not_assessed`.
5. `python3 scripts/check_profile_evidence.py --dir profiles/hardware` (`scripts/check_profile_evidence.py`) або `make check-profile-evidence` ([Makefile](Makefile)).

Власники теми: [docs/HARDWARE-PROFILE-EVIDENCE.md](docs/HARDWARE-PROFILE-EVIDENCE.md) і [profiles/hardware/README.md](profiles/hardware/README.md).

### 4. Робота над інсталятором

Карта «модуль → гарантія» — реєстр [docs/DECISIONS.md](docs/DECISIONS.md); контракт передавання — [docs/INSTALLER-HANDOFF.md](docs/INSTALLER-HANDOFF.md); обов'язкові фази — [agents/skills/installer-lifecycle.md](agents/skills/installer-lifecycle.md). Правте файл, який володіє гарантією, а не сусідній frontend:

| Файл | Гарантія |
| --- | --- |
| `wsm_install/partition.py` | layout як дані; жодного коду, що відкриває блочний пристрій |
| `wsm_install/install_steps.py` | порядок кроків і таблиця `TRUSTED_TOOLS` з абсолютними шляхами |
| `wsm_install/executor.py` | preview-only; runner, verifier і subprocess відсутні |
| `wsm_install/verify.py` | postcondition для кожного дозволеного кроку; невідомий крок лишається `unverified` |
| `wsm_install/disk_identity.py` | повторна ідентифікація цілі перед destructive-фазою |
| `wsm_install/consent.py` | згода на крок, прив'язана до плану й digest команди |
| `wsm_install/journal.py` | append-only журнал із fsync до і після кроку |
| `wsm_install/profile.py` | єдиний валідатор `evidence.json` |
| `wsm_install/preflight_env.py` | перевірки середовища до першого кроку |

Наявність інструментів у дереві, яке виконуватиме інсталятор, перевіряє `python3 scripts/check_tool_closure.py --root ROOT` (`scripts/check_tool_closure.py`). Він навмисно не входить у `make check`: шляхи `TRUSTED_TOOLS` сьогодні FHS, а Guix live image не має `/usr`.

## Перед багатокроковою роботою

1. Прочитайте CONTRIBUTING.md, пов'язаний issue та відповідний task guide/ADR.
2. Звірте актуальний `main`, відкриті issue/PR і власника вже заявленої роботи; узгодьте одну canonical гілку та один PR на логічний результат.
3. Перевірте точні source refs і попередні напрацювання у власних репозиторіях, коли це доречно. Переносьте код або метод лише після перевірки семантики, API/contract, ліцензії й тестів; не переносіть claims без сирих доказів.
4. Відокремлюйте код, який написано, від того, що реально перевірено. Статичний тест, Guix evaluation/build, QEMU TCG/KVM та фізичне обладнання — різні рівні доказу.
5. Новий тест має ловити конкретну регресію: він має бути червоним без виправлення та зеленим із ним. Згадка імені файла або рядка у source не є поведінковим coverage; тестуйте справжній компонент, а не stub. Деталі й приклади — у CONTRIBUTING та `tests/`.

Детальні правила тестування, звітності, синхронізації та злиття визначає [CONTRIBUTING.md](CONTRIBUTING.md); не копіюйте їх сюди.

## Мова та безпека

Українська — канонічна мова документації й інженерних рішень WSM. Переклади, якщо вони потрібні, зберігаються поруч і не суперечать українському оригіналу.

Не запускайте APPLY, форматування, repartition, `guix system init` чи інші disk-writing дії на фізичному диску під час розробки. Для інсталяційного acceptance використовуйте disposable QEMU images. Не додавайте відомі паролі, секрети або приватні ключі в образи, source чи журнали. Preflight і звичайний hardware report мають залишатися read-only.
