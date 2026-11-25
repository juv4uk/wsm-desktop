# Джерела та upstream-документація

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

Цей документ фіксує першоджерела, на які спирається архітектура WSM Desktop. Перед релізом потрібно повторно перевіряти документацію та прив'язуватися до конкретних версій/ревізій, а не вважати посилання на рухому гілку незмінним контрактом.

## GNU Guix

- [GNU Guix](https://guix.gnu.org/) — офіційний сайт.
- [GNU Guix Reference Manual](https://guix.gnu.org/manual/en/) — довідник.
- [Invoking guix system](https://guix.gnu.org/manual/en/html_node/Invoking-guix-system.html) — build, init, vm та інші дії guix system.
- [Channels](https://guix.gnu.org/manual/en/html_node/Channels.html) — канали, автентифікація та відтворення.
- [Creating a channel](https://guix.gnu.org/manual/en/html_node/Creating-a-Channel.html) — вимоги до власного каналу та застереження щодо сумісності API.

## Calamares

- [Calamares project](https://calamares.io/) — офіційний сайт.
- [Module authoring documentation](https://github.com/calamares/calamares/blob/calamares/src/modules/README.md) — типи модулів, Python job modules та їхній контракт.
- [Deployment configuration](https://calamares.euroquis.nl/docs/deploy-configuration) — settings.conf та побудова сценарію встановлення.
- [Developer guide](https://calamares.euroquis.nl/docs/develop-code/) — правила розробки та ліцензування.

Calamares API і формат конфігурації потрібно перевіряти саме для тієї версії, яку WSM вирішить пакувати.

## Nonguix

- [Nonguix upstream repository](https://gitlab.com/nonguix/nonguix) — першоджерело каналу.
- [Nonguix GitHub mirror](https://github.com/nonguix/nonguix) — README та огляд проєкту.
- [Nonguix installation instructions](https://github.com/nonguix/nonguix#installation) — channel introduction та fingerprint.

Nonguix є незалежним community channel. Його інструкції містять застереження щодо nonfree software; WSM Compatibility не є офіційним профілем GNU Guix.

## Ліцензії

- [GPL-3.0-or-later](https://spdx.org/licenses/GPL-3.0-or-later.html)
- [CC-BY-SA-4.0](https://spdx.org/licenses/CC-BY-SA-4.0.html)

## Правило доказовості

Для кожної версії, пакета, драйвера або firmware у майбутньому hardware manifest потрібно зберігати джерело, точну ревізію, ліцензію та результат перевірки. Сам факт присутності компонента в upstream-репозиторії не підтверджує його сумісність з конкретною конфігурацією чи право включати його до WSM образу.
