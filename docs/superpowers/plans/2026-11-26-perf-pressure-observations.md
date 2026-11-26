# План: read-only PSI та zram evidence у performance baseline

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Дата: 2026-11-26
- Канонічна задача: [#151 — вимірюваний baseline boot, services і desktop workloads](https://github.com/juv4uk/wsm-desktop/issues/151)
- Базовий `main`: `c50f09ca661bf1dd27948c4be42fa1fbea9a792d`

## Мета

Під час явного запуску benchmark фіксувати системний memory/CPU/I/O pressure та фактичний стан zram. Не змінювати kernel tunables, zram або zswap; не додавати це до hardware preflight.

## Реалізація

1. Читати `/proc/pressure/{cpu,memory,io}` до та після серії кожного workload. Зберігати `some/full`, avg10/60/300 та дельту cumulative `total` у мікросекундах.
2. Знімати read-only `/sys/block/zram*/{mm_stat,io_stat,bd_stat}`, активний compressor та backing device. Зберігати `mm_stat` як raw before/after (змішані size та page fields), а I/O/backing counters — окремими дельтами.
3. Вказувати system-wide scope: PSI й zram охоплюють усі процеси та не доводять, що затримку спричинив саме benchmark workload.
4. Відсутні файли, старі формати kernel і reset counters подавати як `unknown`/partial; не підміняти їх нулями.
5. Зберегти timed region незмінним: читання telemetry відбувається поза таймерами workload. Немає write у procfs/sysfs.
6. Додати fixture-тести та оновити українську документацію. Зберегти schema v1 як additive fields; підняти producer version до 0.3.0.
7. Зберегти scope system-wide та не робити причинних/регресійних висновків тільки за pressure counters.

## Перевірки

- `python3 -m unittest discover -s tests -p 'test_perf_baseline.py' -v`
- повний `python -m unittest discover -s tests -p 'test_*.py' -v` у GitHub Actions;
- `python scripts/check_docs.py`;
- exact-head CI перед merge.

Не робити performance claims, не змінювати swappiness, zram size/compressor, zswap, governor або power limits. Benchmark workload запускається лише явною CLI-командою, не з preflight.
