# Протокол перевірки мережевої готовності та offline-інсталяції WSM

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Статус: **proposed / validation protocol**
- Пов'язана задача: [#25](https://github.com/juv4uk/wsm-desktop/issues/25)
- Батьківська матриця: [#8](https://github.com/juv4uk/wsm-desktop/issues/8)
- Upstream-аудит: [#4](https://github.com/juv4uk/wsm-desktop/issues/4)
- Контракти: [#12 — installer handoff](https://github.com/juv4uk/wsm-desktop/issues/12), [#24 — scenario capability matrix](https://github.com/juv4uk/wsm-desktop/issues/24)

## 1. Мета та принцип

Протокол визначає, які мережеві докази потрібні для конкретного сценарію встановлення WSM, не перетворюючи «немає Інтернету» на автоматичну несумісність комп'ютера.

**Мережа — це ланцюг незалежних умов, а не один прапорець online:**

виявлений адаптер → driver binding → link/carrier або Wi-Fi association → IP configuration → route → DNS → доступність конкретного потрібного джерела.

Кожен рівень має власний доказ. Успіх попереднього рівня не доводить успіх наступного. Доступність загального Інтернету також не доводить доступність pinned channel, substitute/cache або іншого ресурсу, потрібного обраному backend-профілю.

## 2. Рівні доказів

| Рівень | Доказ | Що можна стверджувати | Що не можна виводити |
| --- | --- | --- | --- |
| N0 — inventory | PCI/USB adapter, interface, explicit parent relationship | Адаптер/інтерфейс виявлено | Що драйвер прив'язаний або мережа працює |
| N1 — driver | sysfs driver binding / відповідний kernel evidence | Драйвер прив'язаний до конкретної функції | Що є carrier, association або IP |
| N2 — link | Ethernet carrier або факт Wi-Fi association, якщо джерело доступне | Фізичний/радіоканал повідомляє про link | Що DHCP, route, DNS або зовнішній endpoint працює |
| N3 — addressing | IPv4/IPv6 address та стан конфігурації | Інтерфейс має адресу | Що існує придатний маршрут до потрібного ресурсу |
| N4 — route | Таблиця маршрутів / route lookup до цільового endpoint | Поточна система має маршрут для конкретного destination | Що DNS або TLS/HTTP endpoint доступний |
| N5 — DNS | Успішне розв'язання конкретного allowlisted hostname | Resolver повернув адресу для цього hostname | Що TCP/TLS або сервіс доступний |
| N6 — endpoint | Явно погоджена перевірка конкретного pinned source/cache endpoint | Цей endpoint відповів у момент перевірки | Що інші дзеркала, всі пакети або весь Інтернет доступні |

Якщо дані відсутні, результат — unknown або not-collected. Не вигадувати «працює» з одного індикатора.

## 3. Read-only інвентаризація

Команди нижче є прикладами для Linux live-середовища. Використовувати лише ті інструменти, які вже присутні; не встановлювати пакети, не піднімати інтерфейси та не змінювати конфігурацію під час preflight.

### 3.1 Інтерфейси й адреси

~~~sh
ip -brief link
ip -brief address
ip route show
~~~

Ці команди показують інтерфейси, адреси й маршрути. Вони не доводять доступність endpoint-а. Перед публікацією редагувати MAC, IP, локальні підмережі, hostname та інші ідентифікатори.

Для окремого інтерфейсу можна читати sysfs carrier, якщо файл доступний:

~~~sh
cat /sys/class/net/INTERFACE/carrier
~~~

Значення carrier не є універсальним доказом Wi-Fi association і не замінює окремої перевірки для wireless.

### 3.2 Драйвер та Wi-Fi

Для PCI/USB функцій використовувати вже зібрані sysfs/modalias/driver-binding докази з hardware report. Не визначати батьківський пристрій мережевого інтерфейсу за назвою або порядком; використовувати explicit topology edge з #18, якщо він присутній.

Для Wi-Fi не запускати scan під час автоматичного preflight. Команда на кшталт iw dev INTERFACE link може показати association, але також розкриває SSID/BSSID та інші локальні дані. Її дозволено використовувати лише в локальному діагностичному режимі з редагуванням цих полів; вони не потрапляють у публічний профіль.

### 3.3 DNS

Якщо systemd-resolved присутній, resolvectl status є read-only способом побачити поточний DNS стан. Вивід може містити адреси DNS-серверів, search domains та interface names — не публікувати його без редагування.

DNS query — це вже мережевий запит. Виконувати його лише для hostname, який належить до конкретного pinned backend source allowlist і потрібен обраному сценарію. Не використовувати довільний домен як «тест Інтернету».

Після allowlisted DNS lookup, якщо потрібно перевірити саме локальний вибір маршруту до отриманої адреси, можна виконати read-only lookup:

~~~sh
ip route get ENDPOINT_IP
~~~

Підставляти лише IP, отриману для дозволеного pinned endpoint. Команда показує, який маршрут обере ядро; вона **не** надсилає пакет і не доводить доступність TCP/TLS/HTTP сервера. Не публікувати повну IP-адресу або локальні gateway/interface details без редагування. Для IPv6 використовувати `ip -6 route get ENDPOINT_IPV6`. Якщо allowlisted hostname має кілька A/AAAA відповідей, за потреби перевірити маршрут до кожної адреси окремо; результат однієї адреси не переносити на інші.

## 4. Endpoint reachability — лише з явною згодою

N6 не є частиною безумовного inventory. Перед перевіркою installer має показати:
- який саме backend/profile обрано;
- який pinned source, substitute або metadata endpoint буде перевірено;
- навіщо цей endpoint потрібен;
- що саме буде відправлено (hostname lookup або короткий HTTPS request);
- що перевірка не завантажує пакети, не додає ключі й не змінює систему.

Перевіряти тільки endpoints, які походять із зафіксованої конфігурації обраного профілю. Не використовувати загальні «speed test», випадкові URL, порт-сканування або довільний список дзеркал.

HTTP HEAD не є універсальним тестом: деякі сервери його не підтримують, а успішний DNS lookup не гарантує TLS/HTTP доступності. Якщо endpoint не підтримує безпечний короткий probe або точний метод не визначений, результат — unknown/not-tested, а не failed.

Не передавати credentials, cookies, особисті токени або повний конфігураційний файл. Не виконувати package fetch/build у межах N6. Доступність substitute перевіряється окремо від доступності upstream source.

## 5. Offline-first рішення

Для кожного сценарію installer має визначити його реальні мережеві залежності за pinned inputs та фактичним станом локального середовища.

| Сценарій | Мережева умова | Поведінка |
| --- | --- | --- |
| Offline install | Усі потрібні inputs/closures уже доступні локально | Можна продовжити без мережі, якщо інші критичні умови виконані |
| Network-assisted install | Конкретні pinned sources/substitutes потрібні для відсутніх inputs | Перевірити саме ці endpoints за згодою; недоступність потрібного джерела блокує лише цей сценарій |
| Optional online features | Оновлення, додаткові пакети, добровільна телеметрія або зовнішня кореляція | Попередження/відкладення; не блокувати базове встановлення |
| Wired fallback | Wi-Fi відсутній, але перевірений Ethernet доступний | Використати Ethernet як альтернативу |
| Offline fallback | Немає робочого network path, але локальні inputs повні | Залишити offline path доступним |

Не припускати, що «пакет є в індексі» означає, що він уже доступний у live image або локальному store. Аналогічно, наявність мережі не доводить, що pinned revision, signing key чи substitute trust налаштовані правильно.

Невідомий стан Wi-Fi не повинен блокувати сценарій, який має перевірений Ethernet або повністю локальні inputs. Невідомий endpoint для обов'язкового відсутнього input може блокувати лише network-assisted сценарій, доки не обрано перевірену альтернативу.

## 6. Privacy та безпека

Не збирати й не публікувати:
- Wi-Fi password, PSK, credentials, tokens, cookies;
- SSID/BSSID, MAC, hostname, повні IP-адреси;
- повний resolver configuration, search domains або локальну топологію мережі;
- повні DHCP leases чи журнали, що можуть містити ідентифікатори користувача.

Не виконувати:
- Wi-Fi scans або password/portal discovery;
- port scans, packet captures, throughput/stress tests;
- автоматичні uploads hardware probes;
- зміну interface state, routes, DNS, firewall чи network-manager configuration;
- встановлення драйверів, firmware або пакетів.

## 7. Результати та profile record

| Результат | Значення |
| --- | --- |
| observed | Локальний факт прочитаний; сам по собі не означає мережеву готовність |
| pass | Конкретний рівень пройшов визначену перевірку |
| fail | Перевірка виконана і конкретна умова не виконана |
| not-tested | Перевірка не запускалася або потребувала згоди, якої не було |
| unknown | Джерело недоступне, суперечливе або недостатнє |

Мінімальний запис для сценарію:
- profile/scenario ID та backend ID;
- environment: VM або physical;
- interface report-local ID і topology evidence або unknown;
- driver-binding source;
- link/address/route/DNS рівні з окремими результатами;
- required endpoint allowlist з джерелом у pinned configuration;
- чи дав користувач згоду на N6;
- endpoint result, timestamp і метод, якщо перевірку виконано;
- local input/closure availability evidence;
- offline alternative та підстави її доступності;
- redacted provenance: tool/version/command.

## 8. Взаємодія з installer-ом

- Не показувати один глобальний прапорець «Internet works» як доказ усіх мережевих вимог.
- Пояснювати, який саме рівень невідомий або не пройшов перевірку.
- Не блокувати offline scenario через відсутність мережі, якщо його потрібні inputs підтверджено локально.
- Не блокувати всі сценарії через відсутність одного мережевого адаптера, якщо є інший перевірений шлях.
- Не пропонувати executable plan для network-assisted сценарію, якщо обов'язкові відсутні inputs не можуть бути отримані з перевіреного джерела.
- Відокремлювати мережеву готовність від довіри до каналів, signing keys та package provenance: це окремі перевірки backend-а.

## 9. Джерела та обмеження

- Linux iproute2: ip link, ip address та ip route мають окремі show/list операції; використовувати тільки read-only форми, не set/add/replace/flush.
- systemd, [resolvectl manual](https://www.freedesktop.org/software/systemd/man/latest/resolvectl.html): status показує поточний DNS стан; query виконує DNS resolution і тому є окремою мережевою дією.
- Конкретні network-manager/iw інтерфейси залежать від live image та версій. Перевіряти локальний --help/man і не вважати їх обов'язковою частиною мінімального preflight.

Цей документ визначає протокол і не стверджує, що будь-яка фізична мережа чи backend endpoint уже перевірені.
