# Публікація пакетів H170 Free та substitute-сервіс

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

## Стан

- Перша публікаційна ціль: **11 upstream Guix package roots** з `drivers/profiles/h170-free-packages.scm`.
- Джерело: лише офіційний GNU Guix channel, зафіксований у `channels.lock.scm`.
- Формат: versioned GitHub prerelease з повною рекурсивною NAR closure, контрольними сумами, provenance та одноразовим публічним ключем Guix archive.
- Довготривалий приватний ключ не зберігається у GitHub Actions або репозиторії.
- Це **пакетний реліз**, а не постійний substitute endpoint чи cache server.

## Перший набір пакетів

Маніфест зафіксований і перевіряється workflow до збірки:

- `linux-libre`
- `mesa`
- `vulkan-loader`
- `vulkan-tools`
- `pciutils`
- `usbutils`
- `alsa-utils`
- `ethtool`
- `nvme-cli`
- `smartmontools`
- `lm-sensors`

Кожен root оцінюється через locked Guix, після чого workflow збирає його derivation, зберігає effective license metadata, store path і recursive NAR hash. До архіву потрапляє повна рекурсивна closure усіх одинадцяти roots, а не лише окремі вихідні каталоги.

## Запуск і публікація

Workflow запускається:
- після злиття зміни publisher-workflow у `main` (path-filtered лише для publisher workflow, lock-файла або H170 Free маніфесту);
- через ручний `workflow_dispatch` з `main`;
- через явний тег `packages-h170-free-*`, що вказує на commit, доступний з `main`.

Він створює одноразовий signing key на ephemeral runner, експортує рекурсивну closure, стискає та ділить bundle на GitHub Release assets менше 1.8 GiB, додає GitHub build provenance attestation, створює prerelease, завантажує assets назад і повторно перевіряє SHA-256 та zstd integrity. Бінарні файли не додаються до звичайних Git-гілок.

## Provenance та імпорт

Реліз містить:
- частини підписаного `h170-free-closure.nar.zst`;
- `signing-key.pub` для конкретного запуску;
- `SHA256SUMS`, digest та розмір bundle;
- точний `channels.lock.scm`, його checksum і опис pinned channel;
- manifest, список package roots, store paths, derivation paths, recursive NAR hashes та closure-size report;
- raw `guix show` metadata з effective license fields;
- `provenance.txt`, `IMPORT.md` та GitHub attestation.

На споживацькій системі спочатку перевірити checksum, окремо перевірити provenance/attestation, свідомо авторизувати лише публічний ключ цього релізу, а потім імпортувати склеєний архів через `zstd -dc | guix archive --import`. Не авторизовувати одноразовий ключ автоматично для майбутніх релізів.

## Межі ліцензії та апаратних тверджень

- Issue [#367](https://github.com/juv4uk/wsm-desktop/issues/367) не блокує upstream-only пакетний набір. `wsm-tools`, `wsm-live-tools` та інші WSM-owned `LicenseRef-Volnist` outputs сюди не входять.
- Не включати NVIDIA FECS/GPCCS blobs, Intel nonfree firmware/microcode, `linux-firmware`, Nonguix чи proprietary NVIDIA driver.
- У locked upstream `linux-libre` 7.3.5 є відома GP107 Nouveau atomic-KMS regression. Отже цей bundle — відтворювана база для H170, але не підтвердження успішного GP107 boot/KMS.
- Окремий `linux-libre-h170` з upstream GP107 fix публікується лише після успішної Scheme evaluation та повної збірки на точному Guix lock.
- Package build, closure і provenance не доводять фізичний boot, NVIDIA binding, KMS, 3D/compute, suspend/resume чи стабільність Gigabyte GA-H170-Gaming 3 + GTX 1050 Ti.

## Substitute service — окремий контур

Постійний substitute endpoint, Pages `.narinfo`, ротація довготривалого ключа та довірена клієнтська конфігурація ще не розгорнуті. Workflow `substitutes.yml` із довготривалим ключем не є джерелом цього одноразового package release. Cuirass залишається build coordinator, а не substitute server.
