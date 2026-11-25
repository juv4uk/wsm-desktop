# Контракт топології обладнання WSM

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Статус: **proposed / review draft**
- Власник контракту звіту: [#5 — versioned hardware evidence report](https://github.com/juv4uk/wsm-desktop/issues/5)
- Власник топології: [#18 — device and interface topology](https://github.com/juv4uk/wsm-desktop/issues/18)
- Пов'язані роботи: [#6 — inventory collector](https://github.com/juv4uk/wsm-desktop/issues/6), [#12 — installer handoff](https://github.com/juv4uk/wsm-desktop/issues/12)

## 1. Мета і межі

Плоский список пристроїв не описує, яка функція належить USB composite device, який драйвер прив'язаний саме до USB-інтерфейсу, який GPU створив DRM-конектор, або до якого контролера належить мережевий чи block device.

Цей контракт пропонує невеликий граф зв'язків усередині одного hardware report. Він має зберігати різницю між:

- **вузлом** — пристроєм або логічним об'єктом, який має власну спостережувану ідентичність у поточному звіті;
- **зв'язком** — спрямованим твердженням між двома вузлами;
- **доказом** — конкретним kernel/sysfs спостереженням або явно описаним похідним висновком;
- **силою твердження** — безпосередньо відкритий ядром зв'язок, детермінований похідний зв'язок або обережно позначена інференція.

Цей документ не визначає фізичну схему материнської плати, не відновлює маршрут кабелю за назвою конектора, не є функціональним тестом і не змінює колектор. Він також не дозволяє використовувати serial/MAC/UUID/WWN як ключі графа.

## 2. Модель даних

### 2.1 Report-local topology

Пропонована форма нового контракту:

```json
{
  "topology": {
    "nodes": [
      {
        "node_id": "node-usb-if-01",
        "kind": "usb-interface",
        "attributes": {
          "interface_number": 1,
          "interface_class": "03",
          "interface_subclass": "01",
          "interface_protocol": "01"
        },
        "evidence": [
          {
            "kind": "live-observation",
            "source": "sysfs",
            "observed_at": "2026-01-01T00:00:00Z",
            "confidence": "confirmed",
            "summary": "Interface attributes read from the canonical sysfs interface node",
            "reference": "/sys/devices/.../1-2:1.1"
          }
        ]
      }
    ],
    "relationships": [
      {
        "relationship_id": "rel-0001",
        "type": "interface-of",
        "from_node_id": "node-usb-if-01",
        "to_node_id": "node-usb-device-01",
        "assertion": "kernel-exposed",
        "evidence": [
          {
            "kind": "live-observation",
            "source": "sysfs",
            "observed_at": "2026-01-01T00:00:00Z",
            "confidence": "confirmed",
            "summary": "Resolved interface path has the USB device as its direct parent",
            "reference": "/sys/devices/.../1-2:1.1"
          }
        ]
      }
    ]
  }
}
```

Це ілюстрація форми, а не готовий JSON Schema або реальний hardware report. Усі ідентифікатори вузлів та зв'язків є випадковими/послідовними лише в межах одного report. Вони не повинні бути стабільними між перезавантаженнями чи різними звітами.

### 2.2 Вузли

Рекомендовані види вузлів:

| `kind` | Призначення | Мінімальні атрибути, якщо доступні |
| --- | --- | --- |
| `inventory-device` | Посилання на пристрій у наявному `devices[]` | `device_ref` на report-local `device_id` |
| `pci-slot-group` | Логічне групування PCI-функцій одного domain:bus:device | Задокументована похідна адреса; не physical-slot ID |
| `usb-interface` | Окрема функція USB composite device | Номер інтерфейсу, class/subclass/protocol, modalias |
| `driver` | Драйвер, на який вказує власний `driver` symlink функції | Назва драйвера; не прирівнювати автоматично до назви module |
| `network-interface` | Netdev або логічний мережевий інтерфейс | Лише безпечні властивості; не MAC та не IP |
| `drm-card` | DRM card, пов'язана з GPU пристроєм | Report-local посилання на inventory device |
| `drm-connector` | Конектор, створений DRM card | Report-local назва/тип, status, modes за наявності |
| `display-sink-observation` | Санітизоване спостереження EDID/status/modes | Лише allowlisted capability facts; без сирого EDID та ідентифікаційних рядків |
| `storage-host` | Виявлений SCSI/NVMe/інший host/controller вузол | Лише доступні безпечні атрибути |
| `block-device` | Block device або namespace | Report-local посилання; без UUID/WWN/serial |
| `sound-card` / `sound-controller` | ALSA card та її спостережуваний device/controller | Лише факти, відкриті конкретним драйвером |
| `hda-codec` / `alsa-endpoint` | Доступний codec/endpoint | Лише за наявності відповідного driver-specific ABI |

Вузол, що представляє наявний `devices[]` запис, має посилатися на його `device_id`; не дублювати ідентичність і не створювати другий незалежний опис того самого пристрою. Для логічних об'єктів, які не є записами `devices[]`, використовується окремий типізований вузол.

Атрибути мають бути типізовані за `kind`; не додавати довільний словник, у який колектор може непомітно записати serial, MAC або інші ідентифікатори. Кожен атрибут повинен мати зрозуміле походження.

### 2.3 Типізовані спрямовані зв'язки

Початковий allowlist:

| Тип | Напрямок | Достатня підстава | Обмеження |
| --- | --- | --- | --- |
| `interface-of` | USB interface → USB device | Канонічний sysfs path та підтверджений безпосередній parent; read-only `bInterfaceNumber`, `bInterfaceClass`, `bInterfaceSubClass`, `bInterfaceProtocol`, `modalias` | Device-level class/driver не описує кожен інтерфейс; binding одного interface не поширюється на sibling interfaces |
| `bound-to` | PCI function або USB interface → driver | Власний resolved `driver` symlink функції | Відсутність symlink не доводить несумісність |
| `function-of` | PCI function → `pci-slot-group` | Однакові domain:bus:device компоненти адреси | Тільки derived logical grouping, не фізичний слот/чип |
| `virtual-function-of` | PCI VF → PF | Явні `physfn` / `virtfnN` symlink | Лише SR-IOV |
| `exposed-by` | DRM connector → DRM card/GPU device | Resolved DRM device links і підтверджена ancestry | `cardN` та connector name — report-time handles |
| `edid-observed-at` | Display-sink observation → DRM connector | Read-only EDID/status/modes, прив'язані до цього connector | Не доводить фізичний кабельний маршрут або працездатність mode |
| `attached-to` | Network/block/sound child → bus device/controller | Канонічний resolved sysfs device link/ancestry | Для virtual/dm/md/loop та непокритих драйверів зв'язок залишається unknown |
| `stacked-on` | Network interface → network interface | `iflink` зіставлений з `ifindex` у тому самому snapshot | Це логічне stacking/linking, не PCI/USB parentage |

Не додавати загальне `connected-to` для монітора лише на підставі connector name, EDID чи `status=connected`. Для цієї інформації існує точніший `edid-observed-at`: він повідомляє, де ядро спостерігало sink data, але не робить висновку про фізичну трасу кабелю.

Новий тип зв'язку потребує таблиці допустимих типів вузлів для обох кінців, напрямку, доказу та негативних прикладів. Не дозволяти вільний текст як тип ребра.

### 2.4 Форма зв'язку

Пропоновані обов'язкові поля:

- `relationship_id`: унікальний лише всередині звіту;
- `type`: значення з allowlist;
- `from_node_id`, `to_node_id`: посилання на вузли цього самого report;
- `assertion`: `kernel-exposed`, `derived` або `inferred`;
- `evidence`: непорожній список provenance-записів.

Для provenance можна повторно використати семантику наявного `$defs/evidence` з #5: kind, source/tool, version/URL за наявності, observed_at, confidence, summary та optional reference. Для sysfs доказу reference має містити лише нормалізований безпечний шлях або його шаблон, а не довільний вивід повного каталогу.

Core collector має випускати лише `kernel-exposed` та обережні `derived` зв'язки. `inferred` дозволяється лише окремим явним шаром, із поясненням правила та без задоволення installation/first-boot critical gate. Не перетворювати відсутній зв'язок на негативний факт.

## 3. Алгоритм збору з sysfs

1. Використовувати `/sys/bus` та `/sys/class` як точки discovery, а не як остаточну топологію.
2. Resolving symlink-ів виконувати до реального `/sys/devices` path.
3. Порівнювати реальні ancestry/parent directories; не покладатися на сталу глибину дерева або порядок обходу.
4. Читати лише documented read-only attributes і власні `driver` symlink-и потрібної функції.
5. Розрізняти stable ABI та testing/obsolete ABI. Testing ABI має бути помічений як provisional, а помилки доступу/відсутність атрибута — як неповне покриття.
6. Для hotplug-sensitive джерел зберігати час snapshot та обробляти `ENOENT`, `EACCES`, `EIO` без фальшивого висновку.
7. Не виконувати bind/unbind, rescan, remove, driver_override, force-probe чи інші записи до sysfs.

Джерело визначення canonical sysfs paths: [Linux sysfs rules](https://docs.kernel.org/admin-guide/sysfs-rules.html). Межі стабільності ABI: [ABI overview](https://docs.kernel.org/admin-guide/abi.html), [testing ABI](https://docs.kernel.org/admin-guide/abi-testing.html).

## 4. Особливі правила для дисплеїв

- `/sys/class/drm/cardN/device` та connector device links треба resolve-ити; зв'язок connector → card створюється лише після перевірки відповідної device ancestry.
- `status`, `modes`, EDID, active mode і функціональний mode test — різні факти.
- EDID — спостереження sink, доступне через конкретний connector; це не доказ, що EDID належить фізичному монітору напряму, а не KVM/dock/forwarded source.
- Парсити EDID лише локально та за потреби; не експортувати сирі байти, serial/name/manufacturer/product strings або ідентифікаційний hash за замовчуванням.
- Не писати в DRM `status` для примусового probing.

Джерела: [DRM KMS](https://docs.kernel.org/gpu/drm-kms.html), [DRM sysfs implementation](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/drm_sysfs.c), [EDID admin guide](https://docs.kernel.org/admin-guide/edid.html).

## 5. Валідація і fail-safe семантика

Schema validation:

- всі `node_id` та `relationship_id` унікальні в межах report;
- кожен `device_ref` посилається на існуючий `devices[].device_id`;
- кожен `from_node_id` і `to_node_id` існує в тому самому `topology.nodes[]`;
- тип зв'язку підтримується, а kind обох кінців відповідає його direction table;
- кожне ребро має хоча б один evidence item і коректний `assertion`;
- однакове ребро не може дублюватися;
- заборонені stable identifiers та raw EDID payloads відхиляються;
- невідомі поля відхиляються у межах кожного типізованого вузла/ребра.

Semantic validation та fixtures:

1. USB composite device з двома interfaces і різними driver bindings; binding одного інтерфейсу не поширюється на sibling.
2. GPU з HDMI та DP connectors; connector ownership підтверджується device ancestry, а EDID observations не створюють фізичної cable edge.
3. Storage controller з двома block devices; ребра існують лише за прямими/derived sysfs ancestry, partition не плутається з controller.
4. Virtual/stacked network interface без bus parent; hardware parent залишається unknown, але `stacked-on` може існувати.
5. Неповний sysfs collector з `EACCES` або hot-unplug; невідомі зв'язки не домальовуються.

Обов'язкові negative tests: dangling references, duplicate edges, unsupported type, wrong direction, empty evidence, inferred edge на critical gate, serial/MAC/UUID/WWN leakage, raw EDID leakage, відсутній driver symlink, відсутній `device` link та відсутній/invalid EDID.

Відсутність edge означає лише «зв'язок не встановлено цим звітом». Вона не означає «зв'язку немає» або «пристрій несумісний».

## 6. Версійність і сумісність

Поточна v1.0.0 schema має root-level `additionalProperties: false`; report-format описує strict validation. Тому нове поле `topology` буде відхилене валідатором v1.0.0. Не додавати його непомітно до v1.0.0 і не називати зміну backward-compatible лише тому, що поле optional.

Рекомендація: зберегти v1.0.0 незмінною і випустити нову major schema revision для topology envelope. У новому контракті старий `devices[]` залишається доступним, а `topology` є окремим графом. Producer пише точну schema version. Consumer, який не підтримує major version, має явно відмовити з поясненням. За потреби можна надати окремий **явний lossy adapter** до v1.0.0, який вилучає topology, додає warning про втрату зв'язків і ніколи не домальовує їх зі старих полів.

До затвердження власником #5 це залишається дизайном, а не новим контрактом. Не змінювати schema, collector, installer handoff або UI до погодження переліку node kinds, edge types та compatibility policy.

## 7. Джерела

- [Linux sysfs rules](https://docs.kernel.org/admin-guide/sysfs-rules.html)
- [Linux ABI overview](https://docs.kernel.org/admin-guide/abi.html)
- [Linux testing ABI](https://docs.kernel.org/admin-guide/abi-testing.html)
- [USB sysfs implementation](https://github.com/torvalds/linux/blob/master/drivers/usb/core/sysfs.c)
- [USB testing ABI](https://raw.githubusercontent.com/torvalds/linux/master/Documentation/ABI/testing/sysfs-bus-usb)
- [PCI sysfs](https://docs.kernel.org/PCI/sysfs-pci.html)
- [DRM KMS](https://docs.kernel.org/gpu/drm-kms.html)
- [DRM sysfs implementation](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/drm_sysfs.c)
- [Network class ABI](https://github.com/torvalds/linux/blob/master/Documentation/ABI/testing/sysfs-class-net)
- [Block device ABI](https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-block-device)
- [ALSA driver API](https://docs.kernel.org/sound/kernel-api/alsa-driver-api.html)
- [HDA codec notes](https://docs.kernel.org/sound/hd-audio/notes.html)
