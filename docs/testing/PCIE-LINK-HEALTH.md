# Протокол read-only перевірки PCIe AER та devlink health

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Статус: **proposed / validation protocol**
- Пов’язана задача: [#69](https://github.com/juv4uk/wsm-desktop/issues/69)
- Матриця тестування: [#8](https://github.com/juv4uk/wsm-desktop/issues/8)
- Upstream tooling audit: [#4](https://github.com/juv4uk/wsm-desktop/issues/4)
- Driver/runtime evidence: [#16](https://github.com/juv4uk/wsm-desktop/issues/16)
- Topology relationships: [#18](https://github.com/juv4uk/wsm-desktop/pull/42)

## 1. Призначення та межі

Протокол описує, як WSM може локально читати доступні PCIe Advanced Error Reporting (AER) counters і, за наявності відповідного драйвера, стан `devlink health`.

Це діагностичні спостереження, а не сертифікат справності PCIe, не функціональний тест пристрою й не глобальний verdict сумісності. Ненульовий лічильник сам по собі не доводить, що конкретний endpoint несправний; нульовий не доводить, що link або пристрій здоровий.

Автоматичний preflight лишається read-only. Заборонені error injection, stress/throughput tests, link retraining, device reset, driver reload, firmware update/flash та recovery процедури.

## 2. PCIe AER: доступні лічильники

Для AER-capable PCI functions ядро може експонувати такі attributes у `/sys/bus/pci/devices/<BDF>/`:

| Attribute | Зміст | Інтерпретація |
| --- | --- | --- |
| `aer_dev_correctable` | Correctable ERR_COR events, повідомлені цією PCI function | Correctable errors; апаратний/програмний стек може виправити їх без втрати функції |
| `aer_dev_nonfatal` | Uncorrectable non-fatal events, повідомлені цією PCI function | Окремий клас uncorrectable errors; сам по собі не доводить відмову пристрою |
| `aer_dev_fatal` | Uncorrectable fatal events, повідомлені цією PCI function | Fatal errors, повідомлені цим компонентом |
| `aer_rootport_total_err_cor` | ERR_COR messages, отримані Root Port | Сукупне спостереження Root Port, не лічильник одного endpoint |
| `aer_rootport_total_err_nonfatal` | ERR_NONFATAL messages, отримані Root Port | Сукупне спостереження Root Port для його PCIe hierarchy |
| `aer_rootport_total_err_fatal` | ERR_FATAL messages, отримані Root Port | Сукупне спостереження Root Port для його PCIe hierarchy |

Device-level attributes доступні лише для компонентів, де ядро експонує AER statistics. Root-port totals доступні лише для відповідних AER-capable Root Ports / Root Complex Event Collectors. Інші attributes можуть бути відсутні через можливості пристрою, ядра або платформи.

**Статус ABI:** ці sysfs attributes задокументовані в Linux `Documentation/ABI/testing/sysfs-bus-pci-devices-aer`, тобто належать до testing ABI, а не до гарантовано стабільного sysfs API. Їхня наявність, назва або формат можуть змінюватися між kernel releases. Кожне evidence record має зберігати `kernel_release`, точну назву attribute, BDF джерела та результат читання. Якщо attribute відсутній, перейменований або його формат не розпізнано, результат — `unknown/not-collected`; не підміняти його нулем і не вгадувати нову назву.

### 2.1 Критичні семантичні обмеження

1. AER counters відображають помилки, побачені або повідомлені саме тим компонентом, на якому прочитано counter. Endpoint-проблема може бути зафіксована link partner або Root Port; сам endpoint може показувати нуль.
2. Root Port totals агрегують повідомлення для PCIe hierarchy. Вони можуть включати помилки, які Root Port бачить у собі; не приписувати їх автоматично downstream endpoint.
3. Один ERR_COR message може представляти кілька correctable errors. Тому `TOTAL_ERR_COR` не обов’язково дорівнює сумі деталізованих записів.
4. Відсутній або unreadable attribute означає `not-collected` / `unknown`, а не нуль.
5. Ненульове значення не є самостійною причиною блокувати інсталяцію; воно може бути накопиченим історичним сигналом.
6. Нульове значення означає лише те, що саме цей counter показує нуль, а не загальну справність.

Реалізація Linux експонує AER statistics через read-only `DEVICE_ATTR_RO` attributes. Інші AER attributes, включно з ratelimit controls, не є частиною цього протоколу й не повинні змінюватися.

## 3. Read-only збір snapshot

Наведена команда призначена для локального діагностичного режиму. Не встановлювати додаткові пакунки заради preflight; читати лише attributes, які вже доступні:

```sh
for attr in /sys/bus/pci/devices/*/aer_dev_correctable \
            /sys/bus/pci/devices/*/aer_dev_nonfatal \
            /sys/bus/pci/devices/*/aer_dev_fatal \
            /sys/bus/pci/devices/*/aer_rootport_total_err_cor \
            /sys/bus/pci/devices/*/aer_rootport_total_err_nonfatal \
            /sys/bus/pci/devices/*/aer_rootport_total_err_fatal; do
  [ -r "$attr" ] || continue
  printf "%s\n" "$attr"
  cat "$attr"
done
```

Для кожного значення report зберігає BDF фактичного джерела, назву attribute, результат читання, kernel release та час спостереження. У зовнішньому звіті використовувати report-local device ID; абсолютний sysfs path не є стабільним public identifier.

Якщо частина attributes недоступна, не переривати весь preflight. Позначати конкретні джерела як `unknown` / `not-collected`.

### 3.1 Один snapshot і delta

Один запуск preflight читає snapshot. Він не повинен називати абсолютне значення «кількістю помилок під час інсталяції» або «поточною частотою помилок».

Delta між двома snapshot-ами можна обчислювати лише за одночасного виконання умов:
- та сама boot session;
- той самий BDF і той самий attribute;
- відомий монотонний порядок часу;
- немає ознак reboot, driver/device reset або зміни джерела.

Якщо лічильник зменшився, boot session змінилася або provenance не збігається — delta є `unknown`. Не припускати, що counter зберігається між reboot або driver reload.

## 4. Attribution через topology

Counter належить PCI function, на якій його прочитано. Щоб пов’язати його з endpoint, потрібні окремі явні topology relationships із #18.

Заборонено:
- приписувати Root Port total найближчому або єдиному endpoint;
- визначати джерело помилки за порядком PCI enumeration;
- вважати endpoint із нульовими counters гарантовано справним;
- об’єднувати Root Port та endpoint counters у спільний total.

Якщо relationship відсутній або unknown, evidence лишається локальним для BDF джерела й не поширюється на інші пристрої.

## 5. Опційний devlink health

Якщо `devlink` уже встановлений і драйвер зареєстрував health reporter, локальний виклик

```sh
devlink health show
```

може показати status/configuration цих reporter-ів. Покриття залежить від конкретного драйвера. Відсутність reporter-а означає `not-available` / `not-collected`, а не «пристрій здоровий».

### Дозволено в автоматичному preflight
- `devlink health show` — лише GET/status/configuration query;
- зафіксувати, що binary/provider відсутній, reporter не зареєстрований або доступ заборонений;
- локально зберігати мінімальний нормалізований результат без vendor/device dumps, які не потрібні для рішення.

### Не запускати автоматично
| Операція | Причина |
| --- | --- |
| `devlink health recover` | Запускає driver recovery та змінює стан пристрою |
| `devlink health test` | Створює тестову health event і може запустити recovery flow |
| `devlink health diagnose` | Викликає driver callback; netlink operation вимагає admin permission |
| `devlink health dump show` / dump-get | За відсутності готового dump драйвер може створити новий |
| `devlink health dump clear` | Видаляє збережений dump |
| `devlink health set` | Змінює reporter configuration, включно з auto-recovery / auto-dump |

Ці команди можуть бути доречні в окремому support workflow, але лише після пояснення мети, оцінки ризику та явної згоди користувача. Вони не є частиною pre-install compatibility preflight.

## 6. Інтерпретація для WSM

| Observation | Що можна сказати | Чого не можна сказати |
| --- | --- | --- |
| AER attributes відсутні | Джерело не зібране або не підтримується | Що PCIe errors відсутні |
| Доступні counters = 0 | Ці counters наразі показують нуль | Що link або пристрій повністю справні |
| Correctable counter > 0 | Компонент повідомив correctable AER events | Що endpoint несправний або помилки тривають зараз |
| Non-fatal / fatal counter > 0 | Компонент повідомив відповідний клас uncorrectable events | Що саме цей endpoint є джерелом без topology attribution |
| Root Port total > 0 | Root Port отримував AER messages у своїй hierarchy | Що конкретний downstream endpoint є винуватцем |
| devlink reporter status доступний | Драйвер експонує reporter і його статус | Що всі функції пристрою працюють |
| devlink reporter відсутній | Provider не надав цей тип evidence | Що пристрій здоровий |

AER / devlink observations можуть підтримати пояснювальне попередження або рекомендацію перевірити hardware, firmware чи cabling у support mode. Вони не повинні самостійно встановлювати hard-stop сумісності, обирати target disk або дозволяти/забороняти backend deployment.

## 7. Acceptance matrix

| Case | Очікуваний результат |
| --- | --- |
| AER tree / attribute відсутній | `not-collected`; preflight продовжується |
| Permission denied | Конкретне джерело `unavailable`; не підміняти нулем |
| Нульові counters | `observed-zero`, не `healthy` |
| Ненульовий correctable | Окреме correctable observation; не hard-stop |
| Ненульовий non-fatal / fatal | Відповідний severity observation із BDF source |
| Root Port total nonzero, endpoint zero | Attribution лишається root-port-local |
| Topology relationship unknown | Endpoint attribution = `unknown` |
| Boot session змінилася | Delta = `unverifiable` |
| Counter regression | Delta = `unverifiable` |
| devlink binary / reporter відсутній | `not-available` / `not-registered` |
| Потрібні diagnose / dump / recover / test | Автоматичний preflight їх не викликає |

## 8. Джерела

- [Linux sysfs PCI AER ABI](https://github.com/torvalds/linux/blob/master/Documentation/ABI/testing/sysfs-bus-pci-devices-aer) — attributes, “as seen/reported” semantics та Root Port attribution.
- [Linux PCIe AER HOWTO](https://www.kernel.org/doc/html/latest/PCI/pcieaer-howto.html) — error classes та модель обробки.
- [Linux AER implementation](https://github.com/torvalds/linux/blob/master/drivers/pci/pcie/aer.c) — `DEVICE_ATTR_RO` counters.
- [Linux devlink health](https://docs.kernel.org/6.19/networking/devlink/devlink-health.html) — reporter lifecycle, dumps та recovery.
- [devlink netlink specification](https://docs.kernel.org/netlink/specs/devlink.html) — GET / SET / RECOVER / DIAGNOSE / DUMP operations і permissions.

Документ визначає безпечні правила збору. Він не стверджує, що будь-який AER counter, devlink reporter або фізичний PCIe link уже перевірено на машині користувача.