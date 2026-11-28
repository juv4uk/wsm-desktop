# Cuirass: збірка всередині Guix

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **інертний прототип; не реєструвати й не запускати до owner Phase B та #367**
- Файли: [`ci/cuirass/specs.scm`](../ci/cuirass/specs.scm), [`ci/cuirass/images.scm`](../ci/cuirass/images.scm), [`ci/cuirass/service.scm`](../ci/cuirass/service.scm)

## Навіщо другий конвеєр

Cuirass — це власний CI GNU Guix. Він не замінює GitHub Actions і не дублює його: вони доводять різні речі.

| Що | Хто доводить |
| --- | --- |
| Образ збирається з зафіксованих каналів | **обидва** — і Cuirass, і workflow |
| Образ завантажується в BIOS і UEFI | **тільки** workflow (QEMU) |
| Інсталятор у носії запускається | **тільки** workflow |
| Заміни доступні іншим | **окремий `guix publish`**, не Cuirass сам по собі |

Cuirass координує збірки через `guix-daemon` і зберігає їхні результати. Він **не** запускає substitute HTTP endpoint сам по собі. Для роздачі substitutes потрібен окремий `guix publish` зі своїм ключем підпису, client trust та мережею; цей етап навмисно не налаштований.

## Дві незалежні дороги до тих самих байтів

`ci/cuirass/images.scm` будує `operating-system-image` з `systems/live-minimal.scm` — те саме, що будує `scripts/build_iso.sh`.

Це навмисна надлишковість: якщо workflow зелений, а Cuirass червоний (або навпаки), одна з двох доріг бреше про ті самі байти. Розбіжність видно одразу, а не через місяць.

## Чому запуск поки заборонений

У WSM channel ще немає owner-signed introduction та `.guix-authorizations`; `channels/wsm.scm` досі є неавтентифікованим development input. Крім того, package allowlist для `wsm-tools` має пройти ліцензійне рішення #367. Тому наведені нижче prerequisites є блокувальними: **не виконуйте `cuirass register`, не запускайте service і не публікуйте substitutes до їх завершення**.

1. Власник виконує Phase B з [документа каналу](GUIX-CHANNEL.md): `.guix-authorizations`, signed introduction, public keyring та `guix git authenticate` без `--disable-authentication`.
2. Перевірити channel inputs у споживачі з точними revisions; Cuirass jobset може відстежувати `wsm/main` лише після того, як кожен fetched revision проходить автентифікацію.
3. Власник закриває #367 і затверджує точний Free package/image allowlist. Compatibility — окремий jobset і окремі locks; не додавати Nonguix до Free.
4. Перевірити service та specifications через `guix system build` / `cuirass register --check` на disposable build host з authenticated inputs. Це ще не означає, що Cuirass було зареєстровано або запущено.

Після виконання prerequisites owner може застосувати цей fragment у `services` окремого build host. `local-file` у [`service.scm`](../ci/cuirass/service.scm) очікує, що конфігурацію оцінюють із кореня репозиторію. Служба за замовчуванням слухає лише `localhost:8081`; не виставляйте цей порт у публічну мережу. Для віддаленого доступу потрібен authenticated TLS reverse proxy/mTLS перед адміністративними маршрутами.

## Що це **не** доводить

- **Не завантажує образ.** У Cuirass немає кроку QEMU, тому зелений job означає «closure збирається», а не «носій стартує».
- **Не перевіряє інсталятор.** Маркер `WSM_INSTALLER_OK` друкує гостя, а гостя тут немає.
- **Не замінює приймання.** Вердикт релізу формується з BIOS/UEFI-свідчень, яких Cuirass не створює.

Тому в матриці вище й стоїть «тільки workflow»: спокуса назвати зелений Cuirass доказом завантаження — саме та підміна, від якої проєкт застерігає.

## Стан

Синтаксис/структуру файлів перевіряють тести в `tests/test_cuirass_specs.py`, але **Cuirass не оцінював jobset, сервіс не розгортався, build ID та build logs відсутні (`NOT_RUN`)**. Green GitHub test не є доказом Guix service evaluation.

Це чесний стан: файли описують, як запустити, а не стверджують, що запущено.
