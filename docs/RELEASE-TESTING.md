# Hardware Preview RC1 — перевірка на реальному обладнанні

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

Ця інструкція описує **read-only** перевірку RC1 на вашому Linux-ПК. Вона не встановлює WSM Desktop, не змінює розділи, bootloader, UEFI або firmware і не вимагає root. Деяка runtime-діагностика може бути недоступна без прав — тоді відповідні поля лишаються `unknown` і з'являється warning. Єдині записи — файли у вказаному вами output-каталозі.

## 0. Що ви отримуєте

Реліз містить:

- `wsm-desktop-0.1.0-rc1-source.tar.gz` — вихідне дерево з фіксованого коміту;
- `SHA256SUMS` — checksum tarball;
- `release-manifest.json` — точний `source_commit`, версія й розміри артефактів.

Реліз **не містить** ISO/USB-образу. Якщо ви хочете перевірити саме завантаження з USB — це окремий наступний крок; status див. у [RELEASE-NOTES.md](../RELEASE-NOTES.md).

## 1. Вимоги

- Linux (будь-який дистрибутив із `/sys` і `/proc`);
- Python 3.10 або новіший;
- `jsonschema[format]==4.26.0` — з `requirements-install.txt` або з системного пакета;
- опційно `/lib/modules/<kernel>/` та `journalctl` або `dmesg` для багатшої діагностики.

Підготовка залежності може потребувати мережі. Після встановлення сам RC1 працює offline. Встановлення залежності ізольовано в користувача (без sudo):

```sh
python3 -m pip install --user -r requirements-install.txt
```

Якщо ваш дистрибутив забороняє `pip install --user`, використайте віртуальне оточення:

```sh
python3 -m venv ~/.venvs/wsm-preview
~/.venvs/wsm-preview/bin/pip install -r requirements-install.txt
~/.venvs/wsm-preview/bin/python scripts/wsm_hardware_check.py --out ...
```

## 2. Перевірка цілісності та запуск

```sh
sha256sum -c SHA256SUMS
tar -xzf wsm-desktop-0.1.0-rc1-source.tar.gz
cd wsm-desktop-0.1.0-rc1
python3 scripts/wsm_hardware_check.py \
  --out "$HOME/wsm-check-$(date -u +%Y%m%dT%H%M%SZ)"
```

Скрипт сам створить каталог із режимом `0700` і відмовиться писати, якщо каталог уже існує й не порожній. Він відхиляє симлінк як кінцевий шлях або будь-який існуючий батьківський компонент, а також ніколи не приймає шлях під `/dev`, `/proc` або `/sys`.

Усі вихідні файли:

```text
report.json               сирий hardware evidence report (schema 1.0.0)
plan-guix.json            diagnostic-only draft plan для guix-system
plan-nix.json             diagnostic-only draft plan для nixos
manifest.json             версія, commit, exit codes, argv-команди, перевірки безпеки
install-guix.stdout.log   стандартний вивід preflight (зазвичай порожній)
install-guix.stderr.log   людський summary + warnings/blockers
install-nix.stdout.log    стандартний вивід preflight (зазвичай порожній)
install-nix.stderr.log    те саме для nixos
hwcheck.*.log             з'являються лише якщо звіт збирається, а не подається через --report
SHA256SUMS                checksum усіх попередніх файлів
```

## 3. Що вважати успіхом

У `manifest.json` перевірте:

```sh
python3 - <<'PY'
import json
from pathlib import Path
m = json.loads(Path("manifest.json").read_text())
print("release:", m["release"]["version"], m["release"]["source_commit"])
print("overall:", m["overall"])
for backend, value in m["plans"].items():
    print(backend, value["status"], "safe:", value.get("safe_execution_flags"))
PY
```

Очікувані значення:

- `overall: "pass"` — обидва плани видано й перевірено;
- `overall: "preflight-blocked"` — звіт зібрано, але один/обидва backend-и зупинилися з exit=3, порожнім stdout і маркером `no plan emitted because required critical evidence is unresolved` у stderr. Це **безпечний результат**, а не помилка скрипта;
- `status: "verified-diagnostic"` для кожного виданого плану;
- `safe_execution_flags: true`, `plan_sha256_matches: true`, `source_report_sha256_matches: true`, `backend_id_matches_request: true`, `confirmable_false: true`.

Перевірте checksum всередині каталогу:

```sh
sha256sum -c SHA256SUMS
```

Якщо `overall: "failed"` — не ігноруйте це. Прикладіть `manifest.json` і відповідні `*.stdout.log` / `*.stderr.log` до issue, але спершу перевірте privacy (розділ 5). У `manifest.json` команди зберігаються як argv-масиви, а шляхи до output замінено на `<out>`.

## 4. Що план не означає

- `plan-guix.json` / `plan-nix.json` — не інсталяційні плани й не дозвіл на запис.
- `plan_readiness.confirmable` завжди `false`.
- `execution.mutations_authorized`, `backend_invoked`, `disk_access_performed` завжди `false`.
- `blockers: []` означає лише «не знайдено critical evidence, яке б зупинило dry-run у цій версії», а не «обладнання повністю сумісне».
- `wsm-hwcheck` 0.2.0 (схема звіту 1.0.0) не запускає функціональних тестів; `driver.status=bound` і наявність firmware-файлу не доводять працездатність.

Детальні правила інтерпретації — в [INSTALLER-PREFLIGHT.md](INSTALLER-PREFLIGHT.md) і канонічному [INSTALLER-HANDOFF.md](INSTALLER-HANDOFF.md).

## 5. Приватність перед надсиланням

Схема 1.0.0 забороняє serial numbers, MAC, UUID, WWN, hostname, username і IP. `manifest.json` не містить абсолютних шляхів до вашого output-каталогу, але `report.json` може розкрити модель і середовище. Перегляньте вміст перед публікацією:

```sh
python3 - <<'PY'
import json
from pathlib import Path
r = json.loads(Path("report.json").read_text())
print("privacy:", r["privacy"])
for d in r["devices"]:
    print(d["device_id"], d["category"], d.get("identity", {}))
PY
```

Надсилайте публічно лише:

- версію з `manifest.json`; якщо `source_commit` має значення `null` (розпакування tarball всередині іншого git-репо), беріть commit із `release-manifest.json`;
- `overall` і статуси `guix`/`nix`;
- стислий human-readable summary зі stderr;
- модель/категорію пристрою й опис проблеми.

Не надсилайте `report.json` цілком без явної згоди: навіть після redaction він може розкрити модель обладнання або середовище. Для публічного issue підготуйте окрему санітизовану копію; чутливі деталі надішліть приватно. Політику див. у [REPORT-FORMAT.md](hardware/REPORT-FORMAT.md).

## 6. Додаткова перевірка збірки (опційно)

На машині з Guix і QEMU можна повторити VM-доказ із #1:

```sh
make check
make describe-lock
make check-locked-system
make vm-system-serial
```

`describe-lock` і `check-locked-system` явно споживають автентифікований `channels.lock.scm`. `vm-system-serial` відповідає proofs-у з #1: disposable QEMU/TCG, серійний вивід і маркер `wsm-desktop login:`. Звичайний `make vm-system` такого маркера не перевіряє. `guix system vm --full-boot` показував `Welcome to GRUB!`, але до ядра не дійшов за 600 секунд, тому bootloader-шлях не вважається підтвердженим. Не запускайте `guix system init` на реальному диску. Зафіксовані результати — у [systems/README.md](../systems/README.md).

## 7. Куди писати результати

- [#10 — hardware-first installer](https://github.com/juv4uk/wsm-desktop/issues/10) — враження від preflight і пропозиції UI;
- [#8 — hardware compatibility matrix](https://github.com/juv4uk/wsm-desktop/issues/8) — фактичні моделі пристроїв і статуси;
- [#1 — Guix VM proof](https://github.com/juv4uk/wsm-desktop/issues/1) — лише питання щодо VM-доказу.

Не відкривайте новий ADR і не змінюйте канонічний handoff-контракт у межах цього RC.
