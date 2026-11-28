# Cuirass: збірка всередині Guix

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **конфігурація готова, інстанс не запускався**
- Файли: [`ci/cuirass/specs.scm`](../ci/cuirass/specs.scm), [`ci/cuirass/images.scm`](../ci/cuirass/images.scm), [`ci/cuirass/service.scm`](../ci/cuirass/service.scm)

## Навіщо другий конвеєр

Cuirass — це власний CI GNU Guix. Він не замінює GitHub Actions і не дублює його: вони доводять різні речі.

| Що | Хто доводить |
| --- | --- |
| Derivation образу на однакових Guix/WSM revisions | **обидва**, коли WSM commit збігається |
| Образ завантажується в BIOS і UEFI | **тільки** workflow (QEMU) |
| Інсталятор у носії запускається | **тільки** workflow |
| Публікація власних substitutes для інших машин | **не налаштована** у поточному сервісному фрагменті |

Cuirass будує **всередині Guix** і зберігає результати в базі та локальному store. Наявні довірені substitutes можуть прискорити отримання залежностей через конфігурацію Guix daemon. Це не означає, що сам сервер публікує власні результати як substitutes: для цього потрібні remote-server/worker, `guix-publish` і ключі підпису.

## Дві дороги до того самого профілю

`ci/cuirass/images.scm` будує `operating-system-image` з `systems/live-minimal.scm` — той самий профіль, що використовує `scripts/build_iso.sh`.

Це навмисна надлишковість. Для порівняння саме тих самих derivations мають збігатися офіційний Guix lock і WSM source commit; Cuirass окремо фіксує фактичний commit каналу під час кожної evaluation. Оскільки WSM тут відстежується через `main`, не називайте будь-який його запуск еквівалентом owner-authenticated release lock.

## Запуск

```sh
sudo -u postgres createdb cuirass

guix shell cuirass postgresql -- \
  cuirass register --specifications=ci/cuirass/specs.scm \
                   --database="dbname=cuirass host=/var/run/postgresql" \
                   --interval=300

guix shell cuirass -- cuirass web \
  --database="dbname=cuirass host=/var/run/postgresql" \
  --port=8081 --listen=localhost
```

Веб-інтерфейс — `http://localhost:8081`. Інтерфейс Cuirass не має власної автентифікації; залишайте його на loopback. Для віддаленого доступу потрібен автентифікований reverse proxy.

Як сервіс — фрагмент у [`service.scm`](../ci/cuirass/service.scm), який вставляється в `services` хост-системи. Файл специфікацій береться як `local-file` із сусіднього `specs.scm`, а не з неіснуючого шляху в системному профілі. Це фрагмент, а не повна декларація: повна стала б другою правдою про те, як налаштовані машини WSM.

## Що це **не** доводить

- **Не завантажує образ.** У Cuirass немає кроку QEMU, тому зелений job означає «closure збирається», а не «носій стартує».
- **Не перевіряє інсталятор.** Маркер `WSM_INSTALLER_OK` друкує гостя, а гостя тут немає.
- **Не замінює приймання.** Вердикт релізу формується з BIOS/UEFI-свідчень, яких Cuirass не створює.

Тому в матриці вище й стоїть «тільки workflow»: спокуса назвати зелений Cuirass доказом завантаження — саме та підміна, від якої проєкт застерігає.

## Стан

Конфігурація написана й перевірена структурно (тести в `tests/test_cuirass_specs.py`). **Інстанс не запускався**: у середовищі розробки немає ні Guix, ні PostgreSQL.

Це чесний стан: файли описують, як запустити, а не стверджують, що запущено.
