# Протокол read-only спостереження PCIe AER та devlink health

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Статус: proposed validation protocol
- Власник: [#69 — safe PCIe AER and devlink health evidence](https://github.com/juv4uk/wsm-desktop/issues/69)
- Пов'язані контракти: #8, #16, #18

## Призначення та межі

Протокол визначає, як WSM збирає пасивні спостереження про PCI Express Advanced Error Reporting (AER) та optional devlink health reporters. Це допоміжні свідчення для support report, не сертифікація пристрою і не самостійний compatibility verdict.

Дозволено: читати вже наявні AER sysfs attributes; за наявності готового інструмента виконати тільки команду devlink health show.

Заборонено: встановлювати iproute2 або модулі; запускати stress/benchmark, error injection, retraining, reset, driver reload або firmware update; змінювати PCIe, driver, device, devlink чи системний стан.

AER counter не є глобальним показником «здоров'я ПК». Його значення прив'язане до конкретного джерела спостереження та класу повідомлень.

## PCIe AER: джерела та семантика

Linux експонує AER статистику через testing sysfs ABI для AER-capable PCI functions.

| Attribute | Значення |
| --- | --- |
| /sys/bus/pci/devices/<BDF>/aer_dev_correctable | Correctable errors, побачені та повідомлені цією PCI function через ERR_COR |
| /sys/bus/pci/devices/<BDF>/aer_dev_nonfatal | Uncorrectable non-fatal errors, побачені та повідомлені цією function через ERR_NONFATAL |
| /sys/bus/pci/devices/<BDF>/aer_dev_fatal | Uncorrectable fatal errors, побачені та повідомлені цією function через ERR_FATAL |
| /sys/bus/pci/devices/<BDF>/aer_rootport_total_err_cor | ERR_COR messages, повідомлені AER-capable root port / root complex event collector |
| /sys/bus/pci/devices/<BDF>/aer_rootport_total_err_nonfatal | ERR_NONFATAL messages, повідомлені root port |
| /sys/bus/pci/devices/<BDF>/aer_rootport_total_err_fatal | ERR_FATAL messages, повідомлені root port |

### As seen/reported — це не attribution до endpoint

Device-level counters показують помилки, які побачив або повідомив саме цей пристрій. Endpoint може спричинити помилку, яку побачить його link partner/root port; root-port counter може зрости, а endpoint — залишитися на нулі. Root-port total counters доступні лише на відповідних AER-capable root ports або root complex event collectors. Вони агрегують повідомлення в PCIe hierarchy за цим root port, включно з повідомленнями від самого root port.

Отже, root-port counter не можна автоматично приписати одному endpoint. Якщо #18 не має явного evidence-backed relationship, endpoint attribution лишається unknown.

### Класи та підсумки

Correctable, uncorrectable non-fatal та uncorrectable fatal — три окремі класи. Не зводити їх до одного числа і не обчислювати глобальний score.

Файл може містити counters окремих типів і TOTAL_ERR_*. Kernel ABI застерігає, що кілька помилок можуть бути повідомлені одним AER message; total message counter тому може не дорівнювати сумі окремих типів. Не додавати підкатегорії до TOTAL_ERR_*.

Ці attributes належать до testing ABI. Записуй фактичний kernel release та назву ABI. Не припускай, що кожне ядро або кожна PCI function експонує всі файли.

## Безпечний збір

Приклад ручного read-only читання одного відомого BDF:

    BDF=0000:00:1c.0
    BASE="/sys/bus/pci/devices/$BDF"
    for name in aer_dev_correctable aer_dev_nonfatal aer_dev_fatal aer_rootport_total_err_cor aer_rootport_total_err_nonfatal aer_rootport_total_err_fatal
    do
      path="$BASE/$name"
      if [ -r "$path" ]; then
        printf '\n[%s]\n' "$path"
        cat -- "$path"
      else
        printf '\n[%s] not-collected (missing or unreadable)\n' "$path"
      fi
    done

У WSM записувати source BDF, точний attribute, counter class, raw numeric values, kernel release, observation timestamp, boot/session context та collector version. BDF — локальна provenance поточного snapshot, а не стабільна міжсесійна ідентичність. Посилання на report-local device_id дозволене лише за точної відповідності; без topology evidence endpoint relationship не створюється.

Зберігати окремо відсутній файл, permission denied, parse error і успішно прочитане значення 0. Не записувати ratelimit attributes під /aer/. Не використовувати setpci, config-space writes, AER injection чи reset paths.

### Snapshot проти delta

Одне читання є snapshot cumulative counter, не швидкістю помилок. Delta можна рахувати лише між двома samples тієї самої boot session, тієї самої BDF/attribute/counter class та kernel/source context, коли монотонний час строго зростає і друге значення не менше за перше.

Boot/session change, BDF/source change, відсутній або регресований timestamp чи зменшення counter роблять delta unknown. Не обчислювати від'ємний приріст і не вгадувати причину reset/wrap.

## Devlink health: тільки optional read query

Reporter-и реалізує конкретний driver. Наявність reporter-а — свідчення експонованого driver health interface; відсутність reporter-а не означає, що пристрій здоровий.

Єдина дозволена команда:

    devlink health show

Запускати лише якщо devlink вже наявний у live environment. Не встановлювати iproute2 і не завантажувати модулі. У devlink netlink specification health-reporter-get є GET operation без admin-perm; це відрізняється від driver callback та state-changing operations. Runtime access може залежати від namespace або policy; failure означає unknown.

| Операція | Семантика | Preflight |
| --- | --- | --- |
| devlink health show / health-reporter-get | Отримує reporter-и та поля стану | Так, optional read-only |
| devlink health diagnose / health-reporter-diagnose | Driver callback, admin permission | Заборонено |
| devlink health dump show / health-reporter-dump-get | Driver dump, admin permission; окремі драйвери можуть створювати dump за запитом | Заборонено |
| devlink health recover / health-reporter-recover | Recovery callback | Заборонено |
| devlink health test / health-reporter-test | Driver test | Заборонено |
| devlink health set / health-reporter-set | Зміна reporter configuration | Заборонено |
| devlink health dump clear / health-reporter-dump-clear | Очищення dump | Заборонено |

Якщо devlink відсутній, доступ заборонено або немає reporter-ів, записати not-collected / permission-denied / no-reporter-exposed. Похідний verdict лишається unknown, а не supported або healthy. Reporter state/error count/recover count/timestamp — окремі driver-provided observations, не end-to-end functional test.

## Правила інтерпретації

| Спостереження | Допустимий висновок | Заборонений висновок |
| --- | --- | --- |
| AER attribute відсутній | not-collected; verdict unknown | Нуль помилок |
| Permission denied/read error | permission-denied або unknown | Нуль або unsupported |
| Counter = 0 | Snapshot конкретного source/counter дорівнює 0 | Повна справність пристрою/лінка |
| Correctable > 0 | Correctable messages observed на конкретному BDF | Автоматично несправний endpoint |
| Non-fatal > 0 | Non-fatal messages observed; потрібен контекст/review | Глобальна несумісність ПК |
| Fatal > 0 | Fatal messages observed; high-priority manual review | Автоматично встановлена причина |
| Root-port total без endpoint counter | Root-port aggregate | Attribution до одного endpoint |
| Topology relationship відсутній | Endpoint attribution unknown | Висновок за сусідством BDF |
| Boot/session змінився між samples | Окремі snapshots; delta unknown | Тренд між boots |
| Counter зменшився | Delta unknown | Від'ємний приріст |
| Reporter відсутній | Reporter не експоновано в snapshot | Reporter/пристрій здоровий |

Абсолютні counters можуть накопичуватися протягом невідомого інтервалу. Кількість повідомлень не є прямою оцінкою severity. Один counter не повинен самостійно блокувати інсталяцію.

## Acceptance cases

Усі cases синтетичні; вони не запускають error injection, devlink callbacks, hardware stress чи driver mutation.

| Case | Input | Очікуваний результат |
| --- | --- | --- |
| A | AER files відсутні | not-collected; unknown, не нуль |
| B | Усі counters дорівнюють 0 | Лише snapshot=0; не healthy |
| C | Correctable counter > 0 | Correctable observation, без hard-stop |
| D | Non-fatal counter > 0 | Non-fatal observation; review |
| E | Fatal counter > 0 | Fatal observation; high-priority review |
| F | Root-port total non-zero, endpoint counter=0 | Root-port aggregate; endpoint unknown |
| G | Topology link до endpoint відсутній | Не створювати endpoint relationship |
| H | Boot/session змінився | Delta unknown |
| I | Другий counter менший | Delta unknown |
| J | Devlink відсутній / reporter list порожній | Optional provider not-collected; не healthy |
| K | Permission denied | Permission-denied/unknown; не нуль |

## Upstream джерела

- [Linux ABI testing overview](https://docs.kernel.org/admin-guide/abi-testing.html)
- [Linux testing ABI files](https://docs.kernel.org/next/admin-guide/abi-testing-files.html)
- [PCI sysfs](https://docs.kernel.org/PCI/sysfs-pci.html)
- [Devlink netlink specification](https://docs.kernel.org/netlink/specs/devlink.html)
- [Devlink documentation](https://docs.kernel.org/networking/devlink/index.html)

Документ є validation protocol. Нові report fields, runtime collector implementation або compatibility verdict rules потребують окремого review власників #5/#6/#16.
