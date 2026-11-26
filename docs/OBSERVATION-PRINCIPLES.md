# Принципи спостереження

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **спільний словник екосистеми**, застосовується в артефактах WSM
- Джерело: [`ecosystem-observer`](https://github.com/juv4uk/ecosystem-observer) — `observation ≠ judgement`, `unknown ≠ false`, `status → source → evidence`
- Перевірка: `tests/test_observation_principles.py`

## Три твердження

**Спостереження ≠ судження.** `wsm-hwcheck` бачить, що пристрій є і що драйвер
завантажений. Він не робить висновку «сумісний». Висновок — це окремий крок із
окремою відповідальністю.

**Невідоме ≠ хибне.** Якщо даних немає, це не «не працює». Це «не перевірено».
Різниця між цими двома станами — це різниця між «ми не знаємо» і «ми знаємо, що
ні», і плутати їх означає викидати робоче залізо.

**Статус → джерело → доказ.** Кожне твердження має вказувати, звідки воно
взялося. Не «працює», а «працює, за `procfs:/cpuinfo`, знімок 2026-11-26».

## Як це виглядає в наших артефактах

| Артефакт | Невідоме | Джерело | Доказ |
| --- | --- | --- | --- |
| `wsm-hwcheck` звіт 1.0.0 | `discovery_status: unknown`, `functional_tests: not-run` | `evidence[].source` (`procfs:/cpuinfo`) | `evidence[].summary` |
| `wsm-cpu-isa/1` | `highest_supported: x86-64-v1` замість вигаданого рівня | `evidence.source` | `levels.*.missing` |
| `wsm-perf-baseline/1` | `storage_class: unknown` | `environment.*` | медіана, p90, MAD |
| `wsm-profile-evidence/1` | `not_assessed` — обов'язковий і непорожній | `report_id` | `verified_functions[].status` |
| `wsm-release-verdict/1` | `not-run` | критерій `id` | `detail` |
| `wsm-install-preflight/1` | `not-run` | критерій `id` | `detail` |

## Чому `storage_class: unknown` — не ліннощі

У `measure_baseline.py` клас сховища завжди `unknown`, хоча його можна вгадати з
імені пристрою (`nvme0n1` → SSD). Вгадування тут порушило б друге твердження:
пристрій міг бути USB-SSD, а `sdX` — взагалі що завгодно. Краще чесно не знати.

## Правило, яке з цього випливає

**Кожен вердикт у проєкті має три стани, не два.** `pass`, `fail` і `not-run`
(або `unknown`, або `not-assessed` — залежно від артефакта). Двостанові
вердикти — це місце, де «не перевірили» тихо стає «перевірили й добре».

## Що це дає разом з іншими репозиторіями

`ecosystem-observer` спостерігає за станом репозиторіїв і контрактів;
`wsm-target-contract` фіксує ABI-ціль; `wsm-os` збирає апаратні спостереження;
`wsm-desktop` збирає докази й будує систему. Спільний словник означає, що
`unknown` у звіті observer-а і `not-assessed` у нашому bundle-і означають одне й
те саме, і читач не мусить здогадуватись.
