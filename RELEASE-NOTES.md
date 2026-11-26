# WSM Desktop RC4 — апаратні докази та preview-only інсталятор

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Версія кандидата: `0.1.0-rc4` (`RELEASE-INFO.json`)
- Дата: 2026-11-26
- Статус: **неопублікований source pre-release; APPLY вимкнено**
- Точний вихідний коміт: буде зафіксований у `release-manifest.json` під час побудови source bundle

## Що змінилося після RC3

**Одна безпечна межа для всіх входів.** CLI `--install`, Guided, TUI та Calamares використовують спільний preview-only executor. Усі заплановані кроки мають статус `not-run` і деталь `command not executed`. Це не «пропущена успішна інсталяція» і не доказ працездатності цільового диска.

**Привілейований агент не виконує команди.** Root-agent перевіряє схему плану та допустимі форми команд, після чого викликає лише preview API. Allowlist — це валідатор форми плану, а не дозвіл на запуск. У executor немає runner, verifier або subprocess API; `dry_run` мусить бути буквальним `True`. APPLY вимкнено незалежно від того, чи процес запущений від root.

**Безпечний запис preview-файлу.** `--write-plan` дозволяє лише валідований regular-file destination та атомарний запис. Device nodes, symlinks і спроби перезаписати hardware report/schema відхиляються до запису.

**Журнал і recovery — read-only.** `--recover` читає заданий журнал і формує звіт. Recovery не запускає команди й не повторює destructive кроки. Відсутній шлях журналу дає контрольовану помилку, а не traceback.

**Preflight завершується до preview.** Перевіряються інструменти, Guix, привілеї, mount point, system file, hardware report та ISA. Це не означає, що диск відкривався або змінювався.

**CI має окремий runtime-рівень.** Єдиний `.github/workflows/ci.yml` розділяє швидкі tests/docs і bounded QEMU acceptance. QEMU gate призначений для generic Linux guest, справжнього `wsm_hwcheck` у no-disk guest, синтетичного CXL Type 3 guest та synthetic ISO через `scripts/qemu_boot_smoke.py`. Сам факт наявності цих jobs не є фізичним hardware verdict або доказом Guix-generated ISO boot.

## Канали та Compatibility

Free і Compatibility мають окремі locks: `channels.lock.scm` та `channels/compatibility.lock.scm`. Структурна product policy перевіряється окремо для кожного lock. Структурна перевірка не доводить криптографічну автентифікацію Guix.

Manual Guix gate окремо оцінює `systems/compatibility.scm` та `systems/live-compat.scm` через Compatibility lock. Для цього source candidate manual Guix authentication/system evaluation ще не виконувалась і не заявляється як успішна. Compatibility є явним nonfree напрямом, а не частиною Free profile.

## Чого в цьому source candidate немає

- **Жодного APPLY.** Немає розбиття диска, форматування, монтування, bootloader write чи Guix deployment.
- **Жодного завершеного встановлення.** Не заявляється install success ні в QEMU, ні на фізичному ПК.
- **Жодного WSM ISO в цьому source bundle.** Мінімальний live image є окремим артефактом і потребує власних build, BIOS та UEFI gates.
- **Жодного фізичного hardware verdict.** QEMU TCG, package declaration, PCI alias або sysfs fixture не доводять функціональність GTX 1050 Ti, Wi-Fi, audio, storage чи реального монітора.
- **Жодного вимірювання продуктивності.** Наявність baseline harness не дорівнює опублікованому physical baseline.

## Як перевірити source bundle

Завантажте source tarball, `SHA256SUMS` і `release-manifest.json` з одного pre-release:

```sh
sha256sum -c SHA256SUMS
python3 -c 'import json; d=json.load(open("release-manifest.json")); n="wsm-desktop-0.1.0-rc4-source.tar.gz"; print(d["source_commit"], d["artifacts"][n]["sha256"])'
```

Tarball будується з точного Git commit через `git archive`; manifest містить `source_commit`, command provenance, розміри та SHA-256 артефактів. Наявність manifest не є доказом, що ISO зібрано або встановлення завершено.

## Відгук і межі звіту

Hardware report може містити manufacturer/model пристроїв. Не публікуйте сирий звіт без окремої перевірки санітизації; serial, MAC, UUID, WWN, hostname, username та IP не повинні потрапляти в публічний issue. Неповні докази мають залишатися `unknown`/`not-assessed`, а невиконані дії — `not-run`, не `pass`.
