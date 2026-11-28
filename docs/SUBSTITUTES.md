# Публікація Guix-пакетів H170 та substitute-сервіс

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

## Поточний стан

- H170 Free upstream package bundle: **дозволено власником 2026-11-28**.
- Package roots: **linux-libre** і **mesa**, лише з офіційного Guix channel, зафіксованого в channels.lock.scm.
- Публікація: успішний запуск пакувального workflow створює версійований GitHub prerelease з повною recursive store closure, контрольними сумами, публічним ключем Guix archive та GitHub build provenance.
- Guix archive signing key: одноразовий ключ daemon на ephemeral runner; приватний ключ не завантажується й не зберігається в репозиторії. Публікується лише signing-key.pub для перевірки та імпорту.
- Substitute endpoint/server: **не розгорнутий**. Цей пакетний release не є substitute cache.
- Cuirass: окремий build coordinator; його конфігурація сама по собі не публікує substitutes.

## Дозволений H170 Free package set

Єдині roots першого пакета:

- linux-libre — kernel candidate з upstream Guix package metadata;
- mesa — userspace candidate для Intel i915 та upstream Nouveau/NVK.

Workflow не завантажує WSM package modules і не бере довільні package expressions із dispatch inputs. Він використовує тільки офіційний pinned channel у channels.lock.scm; WSM channel Phase B/authentication не обходиться й не вимикається.

Публікація запускається тільки явно: tag packages-h170-free-* або workflow_dispatch з main. На push до main автоматичної збірки чи публікації немає. Успішна збірка, експорт повної closure, створення attestation та read-back/checksum verification передують створенню prerelease. Бінарні артефакти не потрапляють у звичайні Git-гілки.

## Provenance та імпорт

Кожен prerelease містить:

- recursive Guix NAR bundle, стиснений zstd і розбитий на частини до 1.8 GiB;
- signing-key.pub для одноразового підпису Guix archive;
- SHA256SUMS та окремий digest зібраного bundle;
- точний channels.lock.scm, channel description і hash lock-файла;
- package roots, store paths, recursive NAR hashes та closure-size report;
- provenance.txt та IMPORT.md.

GitHub Actions додає build provenance attestation до кожної частини архіву. На споживацькій машині спочатку потрібно перевірити контрольні суми, свідомо авторизувати ключ цього конкретного релізу, а потім передати з'єднані частини через zstd у guix archive --import. Ключ не слід автоматично авторизувати для майбутніх релізів.

## Межі ліцензій і апаратної сумісності

Issue #367 залишається відкритим, але не є загальною забороною на сторонні upstream packages. Його межа — WSM-owned програми й артефакти з фактичною LicenseRef-Volnist, зокрема wsm-tools та wsm-live-tools. Їх не включати до публічного package set і не називати GPL, доки власник не визначить коректне effective license metadata.

Не включати в H170 Free closure:

- linux-firmware та NVIDIA GP107 FECS/GPCCS blobs;
- Intel microcode, i915 DMC/GuC/HuC та інші nonfree firmware;
- Nonguix, nvda-580 або інший пропрієтарний NVIDIA driver;
- WSM-owned LicenseRef-Volnist executables.

Окрема ліцензійна межа NVIDIA firmware описана в issue #586 та коментарях до #367. Власницький дозвіл на upstream Free package work не змінює умови сторонньої firmware license.

Профіль drivers/profiles/h170-free.json залишається draft. Package build і store closure не доводять фізичне завантаження, binding, KMS, 3D/compute, стабільність або приймання системи на Gigabyte GA-H170-Gaming 3.

Поточний locked linux-libre candidate має відомий GP107 Nouveau atomic-KMS regression window. Окремий linux-libre-h170 backport не включається в цей release до успішної Scheme evaluation та повної Guix kernel build на точному lock. Відсутність FECS/GPCCS firmware також означає, що GP107 3D/compute у цьому Free bundle не заявляється.

## Substitute service — окремий майбутній контур

.github/workflows/substitutes.yml не є частиною package release. Він потребує довготривалого signing identity, затвердженого endpoint, key custody/rotation/revocation та довіреної клієнтської конфігурації. Жоден секрет GUIX_SIGNING_KEY, довготривалий приватний ключ або substitute URL не створюється цим package workflow.

Cuirass може координувати derivation builds, але не надає HTTP substitute endpoint сам по собі. Розгортання guix publish або іншого substitute publisher потребує окремого рішення та окремих довірених ключів.
