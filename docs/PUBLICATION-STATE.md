# Стан публікації: одна команда замість клікання в UI

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **інструмент** — читає GitHub Release API, нічого не публікує
- Дата: 2026-11-28
- Інструмент: `scripts/publication_state.py`
- Пов'язане: [RELEASE-MINIMAL-LIVE.md](RELEASE-MINIMAL-LIVE.md), [SUBSTITUTES.md](SUBSTITUTES.md), [ISO-RELEASE.md](../ISO-RELEASE.md)

## Питання, на яке відповідає інструмент

«Що опубліковано просто зараз, і чи збігається це з тим, що очікує репозиторій?»

Раніше відповідь вимагала відкривати сторінку релізу в браузері й порівнювати
перелік assets очима. Тепер це одна команда на машині, де `gh` автентифікований:

```sh
python3 scripts/publication_state.py
```

Друкарський звіт читає людина. Для машинного читання або для збереження доказу:

```sh
python3 scripts/publication_state.py --json
```

## Що саме виводиться

Для кожного релізу у вікні перегляду:

- tag, заголовок, дата публікації та `targetCommitish`;
- стан: **опубліковано** чи **чернетка (не опубліковано)**;
- кожен asset із розміром і станом checksum:
  - `manifest` — це сам файл контрольних сум;
  - `listed` / `not-listed` — чи згаданий asset у переданому `SHA256SUMS`;
  - `unknown (manifest not read)` — вміст маніфесту не читався;
- очікуваний набір активів для цього сімейства тегів і те, чого бракує:
  - `missing (required)` — те, без чого реліз не можна вважати повним;
  - `missing (supporting)` — журнали й докази, які workflow завантажує, але
    які не є subject-ами атестації;
- `extra assets` — зайві файли; вони **повідомляються, але не є дефектом**;
- `unknown` — те, чого інструмент не бачить (див. нижче).

Очікуваний набір береться з самого репозиторію, а не з припущення:
`MINIMAL_LIVE_REQUIRED` збігається з переліком у
`scripts/prepare_release_attestation_subjects.py`, а supporting-файли — з того,
що завантажує `.github/workflows/release-minimal-live.yml` і вимагає
`scripts/check_release_readiness.py`. Для тегів `h170-free-cache-*` очікується
`SHA256SUMS`, `signing-key.pub`, `provenance.json`, `metadata.SHA256SUMS` і
хоча б один `*.nar.zst`.

## Що інструмент не бачить і чому це `unknown`

Три речі неможливо побачити з Release API, тому вони ніколи не подаються як
«відсутні»:

1. **Чернетка.** Нічого не опубліковано, а перелік assets може ще зростати.
   Тому чернетка має `published: false`, а її повнота — `unknown`, не «missing».
2. **Workflow-артефакт.** Журнали збірки, provenance-бандли та інші артефакти
   Actions не є release assets, не перелічуються через Release API і спливають
   (типово через 90 днів). Їхня відсутність тут не доводить, що їх не було.
3. **Substitute cache на GitHub Pages.** За [SUBSTITUTES.md](SUBSTITUTES.md)
   `.narinfo`, `nix-cache-info` і `signing-key.pub` розгортаються на Pages, а
   URL існує лише у звіті запуску Actions. Жодного Pages URL у репозиторії не
   зафіксовано, тому інструмент не може сказати, чи кеш обслуговується.

Кожен запис `unknown` має поле `kind`:

- `unresolved` — від нього залежить відповідь, тому verdict стає
  `match-with-unknowns`;
- `limitation` — структурне обмеження, яке не робить кожен запуск
  непереконливим.

Четвертий, менший `unknown`: вміст маніфесту контрольних сум — це asset, а не
метадані. Передайте завантажений файл, щоб отримати `listed`/`not-listed`:

```sh
gh release download 0.1.0-rc6-minimal-live --pattern SHA256SUMS --output SHA256SUMS
python3 scripts/publication_state.py --checksums SHA256SUMS
```

## Перевірка без мережі

JSON, який повертає GitHub CLI, є входом, а не зовнішнім фактом. Тести
подають записаний вивід `gh`:

```sh
python3 tests/test_verify_release_assets.py
```

Прапорці `--releases-json` (вивід `gh release list --json ...`) і
`--release-json` (вивід `gh release view <tag> --json ...`, можна кілька)
вимикають мережу повністю. Ті самі прапорці придатні для того, щоб зберегти
доказ стану на конкретну дату.

## Обмеження та код виходу

Інструмент **лише читає**: єдина поверхня — `gh release list` і
`gh release view`. Він не завантажує, не публікує, не редагує й не видаляє
релізів; тест перевіряє це як властивість коду.

- `0` — звіт сформовано (навіть якщо verdict `mismatch`);
- `1` — лише з `--fail-on-mismatch`, коли опублікованому релізу бракує
  обов'язкового asset-а;
- `2` — некоректний вхід: зламаний JSON від `gh`, недоступний `gh`, поганий
  файл контрольних сум. Помилка друкується одним рядком, без traceback.

`--limit` (типово 10) задає, скільки останніх релізів переглядати. Перелік
ISO у [ISO-CHECKSUMS.sha256](../ISO-CHECKSUMS.sha256) зіставляється з
переглянутими релізами; якщо образ не знайдено, це `unknown` із поясненням, що
він може бути старшим за `--limit`, перейменованим або неопублікованим.
