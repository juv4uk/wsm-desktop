# ADR 0006: Hardware-first frontend WSM — адаптувати патерн archinstall

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Статус: **proposed — на розгляді [#10](https://github.com/juv4uk/wsm-desktop/issues/10); не ратифіковано**
- Дата: 2026-11-25
- Канонічне завдання: [#10 — вибір hardware-first frontend](https://github.com/juv4uk/wsm-desktop/issues/10)
- Джерело оцінки: [#11 — матриця кандидатів](https://github.com/juv4uk/wsm-desktop/issues/11#issuecomment-7170700231) та [доповнення про `guix-install`](https://github.com/juv4uk/wsm-desktop/issues/11#issuecomment-7172014912)
- Пов'язане: [ADR 0004](0004-nix-guix-backend-strategy.md), [#12 / handoff-контракт](../INSTALLER-HANDOFF.md), [#5 — схема звіту](https://github.com/juv4uk/wsm-desktop/issues/5), [#6 — collector](https://github.com/juv4uk/wsm-desktop/issues/6), [#13](https://github.com/juv4uk/wsm-desktop/issues/13), [#14](https://github.com/juv4uk/wsm-desktop/issues/14), [#23](https://github.com/juv4uk/wsm-desktop/issues/23), [#24](https://github.com/juv4uk/wsm-desktop/issues/24), [#2](https://github.com/juv4uk/wsm-desktop/issues/2)
- Переглядає [ADR 0002](0002-calamares-as-installer.md) у частині вибору frontend; його принцип про єдиного власника bootloader залишається чинним.

## Контекст

Попередній напрямок розглядав Calamares як графічний frontend. Подальша оцінка показала, що Calamares не є готовим Guix backend, а користувацький напрямок подальшої роботи — hardware-first інсталятор, який спочатку показує докази про обладнання і лише потім передає керування одному нативному backend-у. Тому Calamares більше не є базовим frontend-ом, хоча його інтеграційні уроки про подвійний bootloader залишаються корисними.

Матриця #11 перевірила archinstall, NixOS installer tooling, Anaconda, YaST/libhd, Debian-installer `hw-detect`, а пізніше — окремий проєкт `guix-install`. Жоден готовий frontend не встановлюється напряму з поточних користувацьких Nixpkgs або Guix package sets: вони є моделями інтеракції або distribution-coupled інструментами, а не залежностями, які WSM може просто додати. Натомість допоміжні пакети для виявлення обладнання доступні в обох системах.

## Актуальний upstream-знімок frontend-патерна (25.11.2026)

Офіційний release log `archinstall` позначає **4.5 від 29.09.2026** як останній реліз на дату цього ADR. Важливі зміни для нашої оцінки:

- upstream перейшов від `curses` до **Textual** для TUI; це зміна UI toolkit, а не причина імпортувати `archinstall` як runtime dependency;
- приклад JSON-конфігурації тепер має окреме тестове покриття;
- `archinstall --dry-run` у guided workflow симулює конфігурацію та зберігає generated config, але цей режим не є WSM safety contract і не замінює нашого typed plan/explicit confirmation.

**Textual 8.2.8** (MIT; реліз 30.06.2026) — окремий Python TUI framework із підтримкою Python 3.9+, Linux/macOS/Windows та можливістю запускати UI у терміналі або браузері. Це новий кандидат для окремої перевірки в прототипі #13 — особливо accessibility, keyboard navigation, live ISO footprint, terminal compatibility та testability. Не додавати його до production dependency set, доки не перевірено package closure у locked Guix/Nix inputs (#39), ліцензію й розмір.

Отже, актуальна рекомендація уточнюється: **адаптувати guided/config/profile workflow archinstall; окремо оцінити Textual як UI toolkit; не залежати від Arch installer або його install engine**.

Джерела:
- [archinstall 4.5 release](https://github.com/archlinux/archinstall/releases) — TUI migration до Textual, JSON config sample tests та release details.
- [archinstall guided configuration and dry-run](https://github.com/archlinux/archinstall/blob/master/docs/installing/guided.rst) — JSON config та безпечна симуляція guided run.
- [Textual 8.2.8 release](https://github.com/Textualize/textual/releases) — upstream version, fixes та релізна історія.
- [Textual documentation](https://textual.textualize.io/) — можливості, cross-platform та terminal/browser execution.


Водночас #1 підтвердив, що мінімальна Guix System будується й запускається у disposable QEMU, а #55 зафіксував вимогу не називати build успішним boot без реального serial-доказу. Це знімає частину невизначеності щодо Guix-шляху, але не вирішує вибір primary backend у #2.

## Рішення

### 1. Власний тонкий frontend за патерном archinstall

WSM розробляє власний тонкий frontend, а не форк будь-якого інсталятора. Як interaction model використовується **archinstall**:

- гідований TUI з послідовними кроками;
- декларативний, перегляданий JSON-план;
- профілі замість довільного меню параметрів;
- цикл перевірки у QEMU до будь-якого запису на цільовий диск.

Це лише `adapt-pattern`. WSM **не** бере Arch payload, не імпортує archinstall як залежність для фінального образу й не дозволяє йому встановлювати bootloader або керувати root filesystem.

### 2. Перший обов'язковий крок — апаратні докази

Frontend показує звіт `wsm-hwcheck` (#5/#6) і похідні рішення для окремих критичних пристроїв, а не один сумарний «compatibility score». Невідомі дані лишаються `unknown`; відсутність functional test не перетворюється на `passed`. Зв'язки USB/DRM/мережі не виводяться з подібних назв чи порядку пристроїв.

Обмеження свіжості сесії обробляються за #23: якщо схема звіту не доводить ту саму boot-сесію, стан є `unverifiable`, а не прихованою перевіркою.

### 3. Один план — один backend — один власник системи

Після preflight frontend формує draft plan і показує його користувачеві. Подальша передача відбувається виключно за канонічним контрактом [#12](../INSTALLER-HANDOFF.md):

- frontend не виконує partition, format, mount для запису, зміни EFI-змінних, встановлення bootloader-а чи `guix system init` / `nixos-install`;
- backend виконує фази `validate → realize/build → prepare → revalidate → apply → verify`;
- для однієї інсталяції обирається рівно один backend: `guix-system` або `nixos`;
- прототип #13 залишається read-only і видає лише `diagnostic-only` план;
- #14 доводить порядок фаз у disposable QEMU.

### 4. Класифікація кандидатів

| Кандидат | Класифікація для WSM | Пояснення |
| --- | --- | --- |
| **archinstall** | `adapt-pattern` | Найкраща модель гідованого TUI, JSON-плану, профілів і QEMU-циклу. Не форкати: payload і bootloader ownership несумісні з WSM. |
| **NixOS installer tooling** | `reference / backend-native` | `nixos-generate-config` — еталон hardware-derived конфігурації; `nixos-install --no-bootloader` — орієнтир для Nix-шляху. Це backend tooling, не GUI frontend. |
| **`guix-install`** | `adapt-pattern` + `reference-only` | Корисні патерни: один install-core для CLI/GUI, `--dry-run` що генерує `system.scm`/`channels.scm`, відновлення після помилки зі звільненням диска. Не брати як production dependency: pre-1.0, режим Panther/Nonguix не відповідає Free-by-default, інтеграція GUI в ISO незавершена. |
| **Debian-installer `hw-detect` / `hwinfo`** | `reference-only` | Еталон firmware/modalias detection і невеликої udeb-сторінки; не є WSM frontend-ом. |
| **Anaconda, YaST** | `reject as frontend for now` | Високий ризик конфлікту за disks/bootloader, distribution-coupled payload і невизначений сучасний addon/handoff шлях. Їхні методи виявлення залишаються джерелом для #4. |
| **Calamares** | `deprioritized` | Більше не базовий frontend. Попередня заборона паралельного bootloader job з ADR 0002 зберігається. |

### 5. Що frontend не робить

- не генерує shell-команди з довільного тексту користувача; backend отримує типізовані поля й allow-listed argv;
- не додає невідомі binary caches, signing keys, nonfree канали чи автоматичний firmware download;
- не надсилає hardware probe у мережу без окремої згоди;
- не пише serial numbers, MAC, UUID чи паролі у звіти й логи;
- не видає `ready-tested` там, де фактично була лише інвентаризація.

## Обґрунтування

Матриця #11 показала, що найсильніше виявлення обладнання має YaST/libhd, а найкраща автоматична генерація апаратного конфігу — NixOS. Проте обидва інструменти тісно пов'язані зі своїм payload і bootloader-ом. Натомість archinstall дає найпридатнішу *форму взаємодії* з користувачем, яку можна адаптувати без успадкування його payload-у. `guix-install` додає корисні Guix-специфічні патерни lifecycle, але його поточні defaults і статус роблять його непридатним як залежність.

Отже WSM інвестує у власний тонкий frontend і спільний product/evidence/plan level, але для першого preview передає підтверджений план лише GNU Guix System — єдиному backend-у, ратифікованому в ADR 0004. Nix/NixOS залишається окремим дослідницьким напрямом поза критичним шляхом; другий backend можливий лише після виконання умов повернення з ADR 0004, із власною реалізацією та без спільного власника root filesystem або bootloader.

## Що може змінити це рішення

- archinstall plugin API виявиться недостатнім без форку або його live-image footprint виявиться неприйнятним;
- з'явиться пакетований, free-by-default і стабільний Guix frontend з перевіреним ISO-шляхом — тоді `guix-install` може перейти з reference-only до кандидата на залежність;
- Anaconda або YaST нададуть задокументований, підтриманий шлях передачі bootloader-а і payload-у без конфлікту;
- з'являться вимірювання installed-size для всіх кандидатів, які змінять оцінку live image;
- стане відомо, чи Leap 16 використовує класичний YaST або Agama у поточному workflow;
- з'являться реальні тести подвійного встановлення bootloader або докази, що hardware preflight блокує валідний сценарій;
- #23/#18/#42 змінять модель свіжості або топології пристроїв;
- #2 обере primary backend і тим самим звузить вимоги до frontend-а.

## Перевірка рішення

Рішення вважається готовим до ратифікації лише разом із:

- read-only прототипом #13 і його black-box тестами;
- QEMU-перевіркою порядку фаз у #14 без запису на фізичні диски;
- виконаним gate #55 для Guix-шляху (`guix system build`, `guix system vm`, реальний login у disposable VM);
- успішним `make check` і відсутністю дублікатів канонічних документів.

## Посилання

- [ADR 0004: GNU Guix першим; Nix/NixOS відкладено](0004-nix-guix-backend-strategy.md)
- [ADR 0002: Calamares як інсталятор](0002-calamares-as-installer.md)
- [Канонічний handoff-контракт #12](../INSTALLER-HANDOFF.md)
- [Issue #1: реальна Guix VM](https://github.com/juv4uk/wsm-desktop/issues/1)
- [Issue #11: матриця оцінки](https://github.com/juv4uk/wsm-desktop/issues/11#issuecomment-7170700231)
- [Issue #11: доповнення про guix-install](https://github.com/juv4uk/wsm-desktop/issues/11#issuecomment-7172014912)
- [archinstall](https://github.com/archlinux/archinstall)
- [guix-install](https://github.com/franzos/guix-install)
- [NixOS Manual](https://nixos.org/manual/nixos/stable/)
- [GNU Guix Manual](https://guix.gnu.org/manual/en/)
