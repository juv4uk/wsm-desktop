# Субститути WSM — publication gate

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Стан: **PUBLICATION_PAUSED / NOT_PUBLISHED**
- Workflow: ручний і fail-closed; він лише пояснює незакриті умови та завершується помилкою.
- Build evidence: окремий upstream-only lane у [PR #773](https://github.com/juv4uk/wsm-desktop/pull/773) (`linux-libre`, `mesa`); це не NAR export і не право на розповсюдження.
- Signing key: не зберігається в repository чи GitHub Actions secrets цим workflow.

## Чому публікація зараз призупинена

Merge #771 увімкнув workflow, який міг зібрати довільний package input, за замовчуванням `wsm-tools`, використати GitHub signing secret і змінювати Releases та Pages. Ця версія замінює той небезпечний шлях fail-closed gate-ом. Жодних substitute assets не було створено.

Потрібні всі умови:

1. **License / redistribution (#367).** Власник має затвердити ліцензію та право розповсюдження кожного WSM-owned package/output. До цього `wsm-tools`, `wsm-live-tools` і Compatibility packages не входять до публічного cache.
2. **Channel trust (#534 / Phase B).** Потрібні owner-signed introduction/history, `.guix-authorizations`, публічний keyring і успішний стандартний `guix git authenticate` consumer. Не приймаються unsigned bypass, вигаданий fingerprint або рухома `main` замість authenticated source.
3. **Key custody.** Окремий owner-ratified ADR має описати генерацію, зберігання, доступ, ротацію, відкликання та incident response. Загальне доручення почати підготовку пакетів саме по собі не задає, де зберігати private signing key.
4. **Immutable package allowlist and provenance.** Для кожного package root мають бути зафіксовані Guix/WSM source commits, derivation/store path, license decision, build evidence і підписаний narinfo. Жодних package names, що передаються довільним shell input.
5. **Endpoint / retention.** ADR має затвердити URL metadata/NARs, доступ, retention, видалення, monitoring і відповідального оператора.

## Дозволена робота до цього моменту

- Перевіряти Guix source/derivations на exact `channels.lock.scm`.
- Збирати upstream-only package roots у тимчасовому store для build evidence, без export або upload.
- Перевіряти `linux-libre`/Mesa та hardware profile окремо; package build не доводить драйверне binding або фізичну роботу H170.

## Що workflow робить зараз

`.github/workflows/substitutes.yml` має лише `workflow_dispatch`, `contents: read` і один крок, який записує `PUBLICATION_PAUSED` у `$GITHUB_STEP_SUMMARY`, після чого завершується ненульовим кодом. Він не встановлює Guix, не читає secrets, не збирає package, не запускає `guix publish`, не змінює Releases чи Pages.

Коли всі умови будуть закриті, потрібен окремий reviewed PR з allowlist-only pipeline, owner-approved signing design і точними provenance gates. Не знімайте цей guard простим перемиканням `if: false` або додаванням signing secret.
