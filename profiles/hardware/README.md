# Профілі заліза

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Кожен перевірений пристрій — це тека `profiles/hardware/<vendor>/<model>/` з
двома файлами:

```
profiles/hardware/asus/h170-pro/
  profile.scm      конфігурація для цієї машини
  evidence.json    докази, що вона справді працює
  artifacts/       файли, що перевіряються за SHA-256
```

**Профіль без `profile.scm` або `evidence.json` не є повним профілем.** Відсутність evidence залишає машину в `diagnostic-only`; неповний каталог відхиляє повний scanner.

## Чому так

Спокуса написати «має працювати» велика, і саме на ній спіткнувся не один
дистрибутив. Різниця між «ми думаємо, що H170 заведеться» і «ми перевірили H170
26 листопада, ось звіт, ось що не працює» — це різниця між обіцянкою і фактом.

`evidence.json` використовує контракт `wsm-profile-evidence/2` і зобов'язаний містити:

- `report_id` зі звіту `wsm-hwcheck` — докази посилаються на джерело;
- `isa_level` — підтверджений рівень `wsm-cpu-isa/1` або явне `unknown`;
- `verified_functions` — що саме перевірено, зі статусом `pass`, `fail` або
  `not-assessed`;
- `known_limitations` — усе, що не працює або працює частково;
- `not_assessed` — **непорожній**: жодна машина не перевірена повністю;
- `artifacts` — непорожній список файлів із відносним POSIX `path` та SHA-256.

Шаблон — [`template.json`](template.json). Скопіюй, заміни значення, але не
залишай вигаданих.

## Чернетка з реального звіту

```sh
python3 scripts/draft_profile_evidence.py \\
  --report hwcheck-report.json \\
  --vendor GIGABYTE --model "H170 Gaming 3" \\
  --slug gigabyte/h170-gaming-3 \\
  --out profiles/hardware/gigabyte/h170-gaming-3/evidence.json
```

Генератор копіює точні байти звіту в `artifacts/wsm-hwcheck-report.json` і записує SHA-256. Це provenance, а не функціональний тест. Кожний `pass`/ `fail` у `verified_functions` повинен окремо посилатися через `evidence` на тестовий артефакт; звіт інвентаризації не може бути єдиним доказом роботи функції.

Генератор не створює `profile.scm`, не змінює статуси з `not-assessed` і не перезаписує існуючі файли.

## Перевірка

```sh
make check-profile-evidence
python3 scripts/check_profile_evidence.py --dir /path/to/hardware-profiles
```

Скрипт відхиляє bundle, якщо:

- жодна функція не має статусу `pass` (усе `not-assessed` — це не доказ);
- функція зі статусом `fail` не згадана в `known_limitations`;
- `verified_by` не є однією з дозволених неперсональних ролей;
- файл артефакту відсутній, не є звичайним файлом або його SHA-256 не збігається;
- `slug` не збігається з текою, у якій лежить файл;
- у модельній теці відсутній `profile.scm` або `evidence.json`.

## Що писати в `verified_by`

Дозволені значення: `автори проєкту`, `local agent`, `web agent`. Особисті імена та електронні адреси не приймаються схемою.
