# Модулі каналу GNU Guix WSM

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Цей каталог є коренем Scheme namespace `(wsm …)` для власних Guix-модулів.

- Пакети: `wsm/packages/`.
- Системні служби й профільні helpers: `wsm/systems/`.
- Метадані каналу: кореневий `.guix-channel`.
- Архітектура, trust model, pinning та H170 release scope: [docs/GUIX-CHANNEL.md](../docs/GUIX-CHANNEL.md).

Не копіювати пакети GNU Guix або Nonguix лише для створення локального дубліката. Перевага — upstream package definitions; власний модуль доречний лише для WSM-specific інтеграції або доведеної прогалини.

Кожне package definition мусить мати точний source origin, version, hash, build system, inputs та фактичну license metadata. Не додавати proprietary binaries без окремого правового й етичного review.

Поточний стан: channel skeleton доданий, але криптографічна автентифікація ще не bootstrap-нута. Не називати канал authenticated, доки немає signed introduction commit, `.guix-authorizations`, keyring branch і успішного `guix git authenticate`. Метадані `wsm-tools` тепер вказують на власну ліцензію WSM через `(wsm licenses)` (`LicenseRef-Volnist`, `file://LICENSE`), а не на GPL. Це не є доказом release readiness: окремо потрібні збірка, виміряна closure, channel trust, а також owner-approved рішення щодо мови реалізації та профілю розповсюдження.
