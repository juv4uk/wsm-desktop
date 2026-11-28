<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

# `wsm_pe_exports` — читач метаданих PE без виконання коду

Невелика програма Free Pascal, яка читає **тільки** заголовки PE/COFF і таблицю
експорту: `MZ`/`PE` сигнатури, machine/bits, розділи, RVA→file offset,
`IMAGE_EXPORT_DIRECTORY`, EAT, таблиці імен і forwarder-рядки. Вона не завантажує
DLL, не викликає жодної експортованої функції й не читає тіло коду.

```sh
make
./wsm_pe_exports /path/to/driver.dll
```

Вивід — один рядок канонічного JSON:

```json
{"format":"pe","machine":"amd64","bits":64,"export_count":2,"exports":[{"ordinal":1,"name":"FxDriverEntryUm","rva":114208,"forwarder":null},...]}
```

Ordinal-only записи мають `"name":null`; forwarded exportи містять рядок у
`"forwarder"`. Похибки (обрізаний файл, відсутня сигнатура, RVA поза розділами,
неправильні лічильники) дають exit code `1` і повідомлення на stderr, а не
частковий JSON.

Це **лише структурний інвентар**. Він не доводить, що функція працює, що DLL
завантажена, що пристрій присутній на H170 або що драйвер має Linux-еквівалент.
Детальні межі й pinned evidence: [OWNER-HARDWARE-REFERENCE.md](../../docs/hardware/OWNER-HARDWARE-REFERENCE.md).

Ліцензія нашого власного коду: `LicenseRef-Volnist`. Жоден vendor-код, дамп або
бінарний файл до репозиторію не додається.
