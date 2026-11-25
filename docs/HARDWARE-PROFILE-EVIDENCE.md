# Докази для профілю заліза

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **контракт v2 реалізовано**, реальних hardware-профілів ще немає
- Канонічна задача: [#171](https://github.com/juv4uk/wsm-desktop/issues/171)
- Схема: [`schemas/profile-evidence.schema.json`](../schemas/profile-evidence.schema.json)
- Перевірка: `make check-profile-evidence`

## Контракт

Профіль — це твердження про конкретну апаратну платформу. Воно має містити:

- `profile.scm` — декларативну конфігурацію;
- `evidence.json` — зв'язаний із конкретним звітом `wsm-hwcheck` набір доказів;
- файли, на які посилається `artifacts`, — логи або результати тестів із перевірюваним SHA-256.

Формат `wsm-profile-evidence/2` є breaking revision від попереднього чернеткового `/1`: тепер `isa_level` і непорожній `artifacts` обов'язкові, кожен артефакт має locator `path`, а `verified_by` — рольове значення. Реальних bundle-ів /1 не було; нові профілі створюються лише у форматі /2.

## Обов'язкові поля

| Поле | Призначення |
| --- | --- |
| `report_id`, `report_schema_version` | точний звіт, на якому базуються перевірки |
| `isa_level` | рівень з `wsm-cpu-isa/1` або явне `unknown` |
| `verified_on`, `verified_by` | дата та неперсональна роль перевіряльника |
| `verified_functions` | функції зі статусом `pass`, `fail` або `not-assessed` |
| `known_limitations` | перелік виявлених обмежень |
| `not_assessed` | непорожній список неперевірених функцій |
| `artifacts` | непорожній список файлів із типом, відносним шляхом і SHA-256 |

Кожен `artifacts[].path` — POSIX-відносний шлях від теки профілю. Абсолютні шляхи, `..`, крапкові сегменти, Windows separators, symlink-и й файли за межами кореня відхиляються. Валідатор повторно обчислює SHA-256 реальних байтів. Без `artifact_root` bundle не може бути визнаний валідним.

## Єдине джерело перевірки

Семантика й перевірка артефактів реалізовані у `wsm_install.profile.problems()`. Її використовують:

- `wsm_install.plan.build_plan()` — для installation preflight;
- `scripts/check_profile_evidence.py` — для перевірки дерева профілів у репозиторії.

Це запобігає ситуації, коли CLI вважає доказ валідним, а installer перевіряє інше правило.

## Прив'язка до апаратного звіту

Планувальник перевіряє, що:

- `profile_evidence.report_id == report.report_id`;
- `profile_evidence.report_schema_version == report.schema_version`;
- кожен артефакт існує під переданим коренем і відповідає своєму SHA-256.

Відсутність evidence — звичайний стан для ще не перевіреної машини: план отримує попередження й залишається `diagnostic-only`. Наявний, але невалідний або прив'язаний до іншого звіту bundle — blocker. Для валідного bundle план зберігає slug, ідентифікатор/версію звіту та SHA-256 самого JSON у `profile_evidence` provenance.

CLI приймає явний read-only аргумент:

```sh
wsm-install --preflight --report report.json --backend guix --dry-run \
  --profile-evidence profiles/hardware/vendor/model/evidence.json
```

Шлях до артефактів у bundle рахується від каталогу цього `evidence.json`; CLI не завантажує й не змінює зовнішніх ресурсів.

## Перевірка дерева профілів

```sh
make check-profile-evidence
python3 scripts/check_profile_evidence.py --dir /path/to/hardware-profiles
python3 scripts/check_profile_evidence.py --file /path/to/evidence.json
```

Повний режим `--dir` вимагає в кожній теці `<vendor>/<model>` обидва файли — `profile.scm` та `evidence.json`. Orphan evidence або profile без evidence відхиляється. Порожній корінь без модельних тек — успішний стан «профілів ще немає». Відсутній корінь — код 2; помилки контракту — код 1.

Режим `--file` перевіряє форму й фактичні байти артефактів, але не перевіряє canonical slug або наявність парного `profile.scm`; для release gate використовується `--dir`.

`check-profile-evidence` входить у `.PHONY`, ціль `make check` і, відповідно, `release-bundle`.

## Межі доказу

- Наразі немає жодного реального hardware-профілю. Шаблон і синтетичні unit fixtures — не свідчення сумісності.
- Відповідність звіту до фізичного пристрою має бути підтверджена збором на цій машині. QEMU, Windows і WSL не замінюють native Linux перевірку фізичного пристрою.
- Формат не доводить, що `report_id` існує в окремому довготривалому сховищі; сховища звітів поки немає.
- Автоматичний вибір профілю за PCI-ID/моделлю ще не реалізований.
- `not_assessed` має залишатися непорожнім: жодна машина не вважається перевіреною повністю.
