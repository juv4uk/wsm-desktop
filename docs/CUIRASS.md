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

Це чесний стан: файли описують, як запустити, а не стверджують, що запущено.
