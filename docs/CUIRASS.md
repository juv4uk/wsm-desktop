# Cuirass: збірка всередині Guix

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **конфігурація готова, інстанс не запускався**
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

## Що це **не** доводить

- **Не завантажує образ.** У Cuirass немає кроку QEMU, тому зелений job означає «closure збирається», а не «носій стартує».
- **Не перевіряє інсталятор.** Маркер `WSM_INSTALLER_OK` друкує гостя, а гостя тут немає.
- **Не замінює приймання.** Вердикт релізу формується з BIOS/UEFI-свідчень, яких Cuirass не створює.

Тому в матриці вище й стоїть «тільки workflow»: спокуса назвати зелений Cuirass доказом завантаження — саме та підміна, від якої проєкт застерігає.

## Стан

Конфігурація написана й перевірена структурно (тести в `tests/test_cuirass_specs.py`). **Інстанс не запускався**: у середовищі розробки немає ні Guix, ні PostgreSQL.

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

## H170 Free package build job

The Cuirass specifications include `h170-free-upstream-packages`. The custom module `ci/cuirass/h170-free-packages.scm` reads the fixed upstream-only manifest `drivers/profiles/h170-free-packages.scm` and creates one Cuirass package derivation job per root for `x86_64-linux`.

The package set is defined and versioned by the pinned official Guix channel. The job resolves derivation metadata; actual package builds are handled by the separate ephemeral GitHub Actions workflow `hw-build-evidence.yml`, which records output NAR hashes and closure sizes in the job summary but does not export or upload NARs.

Neither green derivation evaluation nor a successful ephemeral package build proves GPU driver binding, firmware loading, KMS/3D/compute, ISO boot or native H170 function. The locked Linux-libre 7.3.5 candidate has a documented GP107 Nouveau atomic-init gap; that limitation remains explicit until separately reviewed and resolved.

Do not register the jobset against WSM `main` until owner-controlled Phase B channel authentication has completed. Cuirass service/job execution remains **NOT_RUN**; no PostgreSQL/Cuirass instance is currently deployed. The job does not configure `guix publish`, signing keys, substitutes or release uploads. Those remain governed by #367, #762 and the owner-approved publication decision.