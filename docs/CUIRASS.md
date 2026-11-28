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

## H170 Free upstream package job

The Cuirass specs now include h170-free-upstream-packages. Its roots are read from manifests/h170-free-upstream.scm and converted to one package derivation job apiece for x86_64-linux. The list is pinned by the official Guix channel revision in the spec and is checked for exact package names/versions by tests/guix/source-module-evaluation.scm.

The roots are linux-libre, mesa, intel-vaapi-driver, gptfdisk, parted, dosfstools, e2fsprogs, usbutils and alsa-utils. The custom job resolves derivations; it does not itself build them in the source-evaluation workflow. A real Cuirass scheduler/build remains NOT_RUN.

This is a package collection, not a hardware profile or a validated system configuration. It contains no wsm-tools, proprietary NVIDIA driver, firmware payload, Intel microcode, or i915 DMC/GuC/HuC firmware. Mesa's pinned x86-64 recipe includes the Nouveau Vulkan backend at build time, but GP107 runtime acceleration remains unproven without the firmware and H170 functional tests.

The Cuirass job is not registered against WSM main until owner-signed Phase B channel authentication is complete. It does not authorize NAR export, guix publish, signing-key generation, GitHub Release package assets, or substitute-server deployment; those decisions remain under #367 and docs/SUBSTITUTES.md.