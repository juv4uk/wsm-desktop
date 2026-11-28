# Публікація Guix package outputs і substitutes

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус upstream H170 build: **OWNER_REQUESTED / BUILD_EVIDENCE_ONLY**
- Статус package NAR export / Release assets: **NOT_AUTHORIZED / NOT_PUBLISHED**
- Статус substitute server / `guix publish`: **NOT_CONFIGURED / NOT_PUBLISHED**
- Підписний ключ WSM: **не створений; приватний ключ не передавався в CI**
- Канал WSM: **Phase B не завершена; Cuirass jobset не реєструвати**

## Дозволений шлях зараз: H170 Free upstream build evidence

Вказівка власника дозволяє рухати upstream-only пакетний набір для H170/Skylake/GP107. Канонічний список у `drivers/profiles/h170-free-packages.scm` містить 11 package roots із зафіксованого офіційного Guix channel. У ньому немає WSM-owned `wsm-tools`, Compatibility/Nonguix, proprietary NVIDIA driver, Intel microcode або firmware payloads.

`hw-build-evidence.yml` — manual-only workflow на `main`: він використовує `channels.lock.scm`, збирає точний allowlist на ephemeral runner, записує resolved store paths, NAR SHA-256, closure sizes і channel provenance. Він **не експортує NAR**, не завантажує GitHub artifacts і не додає Release assets. Це дає відтворюваний build evidence, не роздаючи нові бінарники.

PR #761 додає той самий набір до Cuirass custom job і pinned Guix evaluation. Це лише формування derivation jobs; реальний Cuirass instance/job run не запускався.

## Чому зараз не можна експортувати NAR у Releases

`guix archive --export` не є безпідписним архіватором. У pinned Guix source `export-paths` має `sign? #t` за замовчуванням, а `guix archive --export` викликає його без вимкнення підпису:

- [pinned `export-paths` implementation](https://github.com/guix-mirror/guix/blob/4e5195be20d9b124df8a8bb69213412236e4668e/guix/store.scm)
- [pinned `guix archive` CLI](https://github.com/guix-mirror/guix/blob/4e5195be20d9b124df8a8bb69213412236e4668e/guix/scripts/archive.scm)

Під час `guix archive --import` daemon перевіряє цифровий підпис і відхиляє архів, якщо публічний ключ не авторизований у ACL. Отже Release asset без оприлюдненого й авторизованого public key не дає довіреного імпорту. Ефемерний ключ, мовчки створений runner-ом, не вирішує проблему trust: споживачам потрібен незалежно перевірений ключ, а приватний ключ має визначеного власника й процедуру ротації.

Тому старий опис «GitHub Releases без ключа» був технічно неправильним і не повинен використовуватися як publication design.

## Що залишається окремо заблокованим

**WSM-owned пакети — issue #367.** Ліцензійна розбіжність між package metadata та `LicenseRef-Volnist` стосується `wsm-tools` та інших власних програм каналу. У H170 upstream manifest їх немає; дозвіл на upstream-only package work не є ліцензійним рішенням для власного коду.

**Substitute publishing — key custody та endpoint ADR.** Для `guix publish` потрібні окремий publisher, private/public key pair, trusted public-key distribution, client ACL, endpoint, rotation/revocation та incident procedure. Не генерувати ключ у CI, не використовувати довільний `GUIX_SIGNING_KEY` secret без окремого custody-рішення і не копіювати private key у чат.

**WSM channel trust — Phase B / #534.** До owner-signed introduction/history, `.guix-authorizations`, public keyring і успішного звичайного `guix git authenticate` не реєструвати Cuirass jobset проти WSM channel. Не використовувати `--disable-authentication` чи unsigned bypass.

**Firmware/Compatibility — #519/#586.** Intel microcode, i915 DMC/GuC/HuC, NVIDIA FECS/GPCCS, proprietary NVIDIA driver і Nonguix не входять у Free upstream set і не можуть бути додані до нього автоматично.

## Fail-closed workflow policy

- `.github/workflows/hw-build-evidence.yml`: manual-only on main; build/evidence only; no NAR export, no artifacts, no Release assets.
- `.github/workflows/package-archives.yml`: disabled until fixed allowlist, NAR-signing trust and owner-controlled key custody are approved.
- `.github/workflows/substitutes.yml`: disabled until fixed package scope, authenticated provenance, endpoint and signer custody are approved.
- `wsm-tools`, arbitrary package names, firmware and Compatibility packages are excluded.

Не вмикати ці workflows через push, tag, довільний package input або відсутність секрету. Відсутність ключа — причина відмовити в publication, а не запрошення автоматично створити новий.

## Статус на зараз

Жоден WSM substitute cache чи package NAR archive не опублікований. H170 upstream build-evidence lane готується в PR #761; до його merge і успішного точного Guix build run не заявляти навіть package build PASS. Це не native H170 hardware PASS і не доказ GPU runtime.
