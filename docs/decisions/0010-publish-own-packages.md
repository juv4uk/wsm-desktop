# ADR 0010: публікація власних пакетів каналу

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **прийнято** — пряма вказівка власника, 2026-11-28
- Дата: 2026-11-28
- Пов'язане: #367, wsm-tools, .github/workflows/wsm-tools-rc7-release.yml

## Рішення власника

Власник дозволив розповсюдження **зібраних бінарників власного коду WSM**. Це рішення закриває питання дозволу для самого WSM-owned package output; воно не оголошує LicenseRef-Volnist OSI/FSDG-ліцензією і не означає acceptance цього custom license record upstream Guix.

Публікуються лише власні пакети WSM. Ядро Guix, Mesa, Nonguix, proprietary NVIDIA driver, NVIDIA firmware та Intel microcode мають окреме походження й окремі ліцензійні межі; дозвіл на WSM tools не поширюється на них.

## Одноразова публікація RC7

Власник повторно й прямо вимагає негайної публікації пакетів та артефактів. Для виконання цього рішення дозволено **один** публічний pre-release wsm-tools 0.1.0-rc7 після успішного locked Guix evaluation/build, GitHub Artifact Attestation, SHA-256 перевірок і read-back перевірки Draft Release.

Одноразовий workflow .github/workflows/wsm-tools-rc7-release.yml запускається лише створенням гілки publish/wsm-tools-rc7. Ця гілка має містити те саме Git tree, що й актуальний main; workflow перевіряє рівність дерев і створює Release, націлений **на commit default main**, а не на trigger branch. Це важливо: GitHub відхиляє GITHUB_TOKEN з contents: write, коли Release target додає або змінює .github/workflows/** відносно default branch і потрібен додатковий Workflows: write; токен Actions не може отримати цей permission. Публікація з target, що вже є commit default branch, не потребує PAT або Workflows: write.

Порядок обов'язковий:
1. guix time-machine -C channels.lock.scm на офіційному автентифікованому Guix lock; Codeberg rewrite змінює лише transport.
2. Перевірка Scheme module evaluation для RC7 package metadata і GP107 kernel overlay.
3. guix pack self-contained tar.zst з python-minimal, усіма трьома WSM CLI, schemas і share/doc/wsm-tools/LICENSE.
4. Provenance, checksums і GitHub Artifact Attestation.
5. Створення Draft Release, завантаження assets назад та повторна перевірка кожного SHA-256 і структури archive.
6. Зняття draft лише після успіху всіх перевірок.

Цей workflow — **одноразовий виняток** для RC7, а не загальний push-trigger для наступних пакетних релізів. Наступні RC/версії вимагають окремого явного рішення власника. package-archives.yml лишається read-only перевіркою фіксованого H170 Free plan; він не є WSM tools publisher.

## Межі підпису й substitute cache

Сам guix pack для WSM tools не потребує постійного Guix signing key. Для H170 Free upstream substitute workflow використовується ephemeral per-run signing key: private key залишається на тимчасовому runner, public key та provenance публікуються з конкретним набором NAR. Це не постійний owner signer і не додає wsm-tools до 11-пакетного upstream Free manifest.

Заборонено:
- додавати бінарні артефакти до звичайних Git branches;
- вимикати Guix channel authentication або змінювати pinned commit/fingerprint заради швидкості;
- публікувати Nonguix, NVIDIA proprietary driver, NVIDIA firmware чи Intel microcode в H170 Free;
- заявляти фізичну H170/GP107 acceptance на підставі одного лише package build.

## Статус доказів

- wsm-tools 0.1.0-rc6 був зібраний і перевірений; відповідний GitHub Release зараз є **Draft**, тобто не вважається публічним релізом.
- RC7 recipe використовує python-minimal, містить WSM LicenseRef-Volnist metadata та встановлює LICENSE у runtime. RC7 не вважається опублікованим до нового locked build, attestation, read-back і зняття Draft.
- H170 Free substitutes та linux-libre-h170 GP107 kernel — окремі артефакти з окремими acceptance gates. Package build не доводить boot, Nouveau binding, KMS, 3D/compute, suspend/resume чи physical hardware runtime.
