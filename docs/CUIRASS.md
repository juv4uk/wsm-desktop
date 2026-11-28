# Cuirass: збірка всередині Guix

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **локальна build farm розгорнута й працює на Ubuntu 24.04 WSL2** (2026-11-28, EET); деталі — [«Локальна build farm»](#локальна-build-farm-на-ubuntu-2404-wsl2)
- Файли: [`ci/cuirass/specs.scm`](../ci/cuirass/specs.scm), [`ci/cuirass/images.scm`](../ci/cuirass/images.scm), [`ci/cuirass/service.scm`](../ci/cuirass/service.scm)

## Навіщо другий конвеєр

Cuirass — це власний CI GNU Guix. Він не замінює GitHub Actions і не дублює його: вони доводять різні речі.

| Що | Хто доводить |
| --- | --- |
| Образ збирається з зафіксованих каналів | **обидва** — і Cuirass, і workflow |
| Образ завантажується в BIOS і UEFI | **тільки** workflow (QEMU) |
| Інсталятор у носії запускається | **тільки** workflow |
| Заміни доступні іншим | **тільки** Cuirass |

Третій рядок — причина існування Cuirass. Він збирає **всередині Guix** і віддає результати як substitutes, тобто наступна збірка не переробляє той самий closure з нуля.

## Дві незалежні дороги до тих самих байтів

`ci/cuirass/images.scm` будує `operating-system-image` з `systems/live-minimal.scm` — те саме, що будує `scripts/build_iso.sh`.

Це навмисна надлишковість: якщо workflow зелений, а Cuirass червоний (або навпаки), одна з двох доріг бреше про ті самі байти. Розбіжність видно одразу, а не через місяць.

## Запуск

```sh
sudo -u postgres createdb cuirass

guix shell cuirass postgresql -- \
  cuirass register --specifications=ci/cuirass/specs.scm \
                   --database="dbname=cuirass host=/var/run/postgresql" \
                   --interval=300

guix shell cuirass -- cuirass web --database="dbname=cuirass host=/var/run/postgresql"
```

Веб-інтерфейс — `http://localhost:8081`.

Як сервіс — фрагмент у [`service.scm`](../ci/cuirass/service.scm), який вставляється в `services` хост-системи. Це фрагмент, а не повна декларація: повна стала б другою правдою про те, як налаштовані машини WSM.

## Локальна build farm на Ubuntu 24.04 WSL2

Розгорнуто 2026-11-28 (EET) без Guix System, без `guix system reconfigure`, без remote builders.

### Фактичні компоненти

| Компонент | Стан |
| --- | --- |
| Ubuntu | 24.04.5 LTS, ядро `6.18.58.1-microsoft-standard-WSL2`, systemd `running` |
| Ресурси | 4 × Intel Core i5-6400, 16 GB RAM, 827 GB вільно на `/` |
| Системний GNU Guix | `/usr/local/bin/guix` → 1.5.0 (`guix` у PATH — з Nix, не використовується) |
| `guix pull` | Автентифікований канал `guix` на commit `4a10484454a376234d4f8603ba3bea93f51314e6` |
| `guix-daemon` | `active`, непривілейований `guix-daemon` (UID 999), socket `0666`, substitute-сервери Bordeaux + ci.guix.gnu.org |
| PostgreSQL | 16.15 з APT, cluster `16/main online`, Unix socket `/var/run/postgresql`, peer auth |
| Cuirass | **1.3.7** з офіційного Guix-каналу (pinned `4e5195be…`), профіль `/var/lib/cuirass/profile` |
| Сервісний користувач | `cuirass:cuirass`, home `/var/lib/cuirass`, shell `/usr/sbin/nologin` |
| Nix | `nix (Nix) 2.35.4`, не змінювався |

### systemd та шляхи

- `/etc/systemd/system/cuirass-register.service` — `cuirass register` із `-S /etc/cuirass/specifications.scm`, `-D 'dbname=cuirass host=/var/run/postgresql'`, `--interval=300`, `--threads=1`, `--parallel-evaluations=1`, `--fallback`, TTL 30d/60d/24m/4w (`24m` у Cuirass означає 24 місяці — у журналі `62208000s`).
- `/etc/systemd/system/cuirass-web.service` — `cuirass web` на `127.0.0.1:8081`, два потоки.
- Обидва: `User=Group=cuirass`, `CUIRASS_STATE_DIRECTORY=/var/lib/cuirass`, `XDG_CACHE_HOME=/var/cache/cuirass`, `Restart=on-failure`, journald.
- `/etc/cuirass/specifications.scm`, `/etc/cuirass/parameters.scm` (без секретів).
- `/var/lib/cuirass/profile` — стабільний профіль Cuirass; `/var/lib/cuirass/run/cuirass/bridge` — bridge до register.
- `/var/cache/cuirass/guix/checkouts` — Git-кеш каналів (Cuirass 1.3.7 бере `$XDG_CACHE_HOME/guix/checkouts`, а не `--cache-directory`).
- GC roots: `/var/guix/gcroots/profiles/per-user/cuirass/cuirass`.

### Специфікація

Специфікація вказує на гілку `channel/wsm-guix`, бо вона містить source-only self-build і виправлену `(license …)`. Після злиття PR #837 треба перевести специфікацію на `main`.

```scheme
(define %wsm-channel
  (channel
   (name 'wsm)
   (url "https://github.com/juv4uk/wsm-desktop")
   (branch "channel/wsm-guix")))

(list
 (specification
  (name 'wsm-tools)
  (build '(packages "wsm-tools"))
  (channels (list %wsm-guix-channel %wsm-channel))
  (systems '("x86_64-linux"))))
```

`(build '(channels wsm))` тут навмисно не використовується: він би взяв і `linux-libre-h170` — важкий kernel-кандидат, ще не перевірений як bootable.

### Команди

```sh
# статус
systemctl status cuirass-register.service cuirass-web.service
curl -sS 'http://127.0.0.1:8081/api/evaluations?spec=wsm-tools&nr=10'
curl -sS 'http://127.0.0.1:8081/api/latestbuilds?nr=10'
curl -sS 'http://127.0.0.1:8081/api/queue'

# ручний evaluation
curl -X POST http://127.0.0.1:8081/jobset/wsm-tools/hook/evaluate

# перезапуск і журнали
sudo systemctl restart cuirass-register.service cuirass-web.service
journalctl -u cuirass-register.service -f
journalctl -u cuirass-web.service -f

# база
sudo -u postgres psql -d cuirass -c 'SELECT id, specification, status FROM builds ORDER BY id DESC LIMIT 10;'
```

API 1.3.7 — Hydra-подібний: `/api/jobs`, `/api/evaluations?spec=…&nr=…`, `/api/latestbuilds?nr=…`, `/api/queue`; окремий evaluation — `/api/evaluation?id=…`.

### Спостереження за сервісами

- Після старту `cuirass-register.service` написав `opening bridge socket at /var/lib/cuirass/run/cuirass/bridge`, `builds will be made via the local build daemon`, створив схему БД (13 таблиць) і зареєстрував jobset `wsm-tools`.
- `cuirass-web.service` слухає тільки `127.0.0.1:8081`; `curl http://127.0.0.1:8081` → `HTTP 200`.
- Під час одночасного перезапуску обох юнітів веб один раз вийшов із кодом 1, бо bridge register ще не був готовий. `Restart=on-failure` підняв його через 10 с; повторний `curl` знову дав `HTTP 200`. Це спостереження auto-recovery, а не ознака стабільності конфігурації.
- `cuirass register --check` до запуску дав `all good!` (з harmless warning про deprecated `load*`).

### Резервні копії

Перед записом у `/etc` створено `/var/backups/cuirass-20261128-083405`. На момент встановлення `/etc/cuirass`, `/var/lib/cuirass`, `/var/cache/cuirass` і systemd-юнітів Cuirass не існувало, тому копіювати було нічого; каталог створено для майбутніх змін. Жодну наявну базу чи конфігурацію не перезаписано.

## Що це **не** доводить

- **Не завантажує образ.** У Cuirass немає кроку QEMU, тому зелений job означає «closure збирається», а не «носій стартує».
- **Не перевіряє інсталятор.** Маркер `WSM_INSTALLER_OK` друкує гостя, а гостя тут немає.
- **Не замінює приймання.** Вердикт релізу формується з BIOS/UEFI-свідчень, яких Cuirass не створює.

Тому в матриці вище й стоїть «тільки workflow»: спокуса назвати зелений Cuirass доказом завантаження — саме та підміна, від якої проєкт застерігає.

## Стан

Структурні тести в `tests/test_cuirass_specs.py` і далі перевіряють specification-файл репозиторію. Окрім того, на цій машині тепер є реальний інстанс: PostgreSQL 16, Cuirass 1.3.7, обидва systemd-сервіси й локальний daemon. Перший контрольний evaluation після ручного POST на `/jobset/wsm-tools/hook/evaluate` ще обчислює похідну pinned Guix; поки що API повертає порожні `/api/evaluations` і `/api/latestbuilds`. Вебінтерфейс — лише подання даних бази, а не доказ складання.

## Що було виправлено після звірки з посібником

Перша редакція цих файлів була написана «на віру» і містила чотири помилки, які виявила звірка з офіційними джерелами:

| Було | Стало |
| --- | --- |
| `(wsm ci images)` — модуль не резолвився, файл лежить у `ci/` | `(ci cuirass images)` — namespace збігається з шляхом |
| `(operating-system-image os #:target system)` — такої процедури немає | `(system-image image)` у монадичному store, без `#:target` |
| `(assq-ref arguments 'system)` — Cuirass передає `systems`, список | `(assq-ref arguments 'systems)` |
| `(gnu services ci)` — там Laminar і Forgejo | `(gnu services cuirass)` |

Плюс `use-substitutes?` — не поле `cuirass-configuration`, і `load` з `/run/current-system` не працює в пісочниці збірки, тому специфікації вбудовані як gexp.

Це і є причина, чому файли такого роду не можна писати без джерела: кожна з чотирьох помилок дала б збій лише в момент запуску, на машині, де Guix є, — тобто не в того, хто писав.

Це чесний стан: файли описують, як запустити, а не стверджують, що запущено.
