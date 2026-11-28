# Профілі заліза

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Цей каталог призначений лише для **оголошених апаратних профілів**. Довідкові
спостереження, неперевірені конфігурації та нотатки про власне обладнання
зберігаються в `docs/hardware/`, а не серед профілів.

Коли профіль буде реально заявлено, його каталог має містити:

```text
profiles/hardware/<vendor>/<model>/
  profile.scm
  evidence.json
  artifacts/
```

- `profile.scm` — декларація конфігурації для конкретної машини. Починайте з [`template.scm`](template.scm) для Free/Linux-libre candidate (це не Compatibility перемикач): він містить `ЗАМІНИТИ` у кожному місці, яке треба заповнити з реальної машини, і жодного значення, яке можна залишити за замовчуванням.
- `evidence.json` — bundle зі звітом `wsm-hwcheck`, перевіреними функціями
  та обмеженнями.
- `artifacts/` — незмінні raw reports і функціональні logs, адресовані з bundle.
- Не створюйте каталог профілю лише на підставі Windows/WSL інвентаризації,
  synthetic classifier test або припущення про драйвер. Відсутність профілю
  є чесним станом, доки немає native Linux evidence.

Дослідницькі спостереження про H170 власника з Windows/WSL винесені в
[окрему довідку](../../docs/hardware/OWNER-HARDWARE-REFERENCE.md). Вона не є
апаратним профілем, не створює `evidence.json` і не бере участі в
автоматичному зіставленні. Профіль з'явиться лише після native Linux report
та окремих функціональних тестів.

## Контракт `wsm-profile-evidence/2`

Запуск повного scanner-а:

```sh
make check-profile-evidence
python3 scripts/check_profile_evidence.py --dir profiles/hardware
```

Bundle має містити:

- `report_id` та `report_schema_version` — посилання на exact source report;
- `profile_source.path` і `profile_source.sha256` — digest точних байтів
  `profile.scm`, на яких виконувалися тести;
- `isa_level` — підтверджений рівень `wsm-cpu-isa/1` або явне `unknown`;
- `verified_functions`, `known_limitations` і непорожній `not_assessed`;
- непорожній `artifacts` із безпечними relative POSIX paths і SHA-256.

Bundle містить **рівно один** артефакт типу `wsm-hwcheck-report`. Це provenance
інвентаризації, не функціональний тест. Кожен `pass` або `fail` мусить
посилатися через `verified_functions[].evidence` на окремий
`functional-test-log`; посилання лише на report відхиляється. Файли мають
бути звичайними непорожніми файлами в `artifacts/`; symlink, traversal,
дубльовані шляхи й неправильний digest відхиляються.

## Чернетка з реального звіту

У цільовій теці до генерації вже мають існувати `profile.scm` і всі потрібні
права доступу. Генератор не створює декларацію профілю, не робить
функціональних тестів, не змінює статуси з `not-assessed` і не перезаписує
наявні файли:

```sh
python3 scripts/draft_profile_evidence.py \
  --report hwcheck-report.json \
  --vendor GIGABYTE --model "GA-H170-Gaming 3" \
  --slug gigabyte/ga-h170-gaming3 \
  --out profiles/hardware/gigabyte/ga-h170-gaming3/evidence.json
```

Генератор копіює точні байти report до
`artifacts/wsm-hwcheck-report.json`, зберігає SHA-256 і хешує точні байти
`profile.scm`. Після цього людина мусить виконати функціональні тести,
додати їхні logs до `artifacts/` і вказати окремі шляхи в кожній перевіреній
функції. Draft bundle із самими `not-assessed` не проходить semantic evidence
gate і не стає профілем сумісності.

## Межа доказів

SHA-256 підтверджує збіг фактичних байтів із digest, але не засвідчує автора,
code review, походження commit або підпис WSM. `profile.scm` є виконуваним
Guile Scheme-кодом; перевірка цілісності не є дозволом на його виконання.
Наразі профілів із реальними функціональними доказами немає. Див.
[HARDWARE-PROFILE-EVIDENCE.md](../../docs/HARDWARE-PROFILE-EVIDENCE.md).
