# H170 Free — субститути Guix

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Workflow: .github/workflows/substitutes.yml
- Маніфест: drivers/profiles/h170-free-packages.scm
- Guix inputs: channels.lock.scm — зафіксований офіційний Guix, без додаткових каналів
- NAR assets: незмінний GitHub Release для кожного cache snapshot
- .narinfo, nix-cache-info, public key та provenance: GitHub Pages
- Публічний cache workflow: запускається після релевантного merge в main або вручну

## H170 Free package roots

Початковий кеш містить десять upstream Guix package roots:

- mesa, vulkan-loader, vulkan-tools
- pciutils, usbutils, alsa-utils
- ethtool, nvme-cli, smartmontools, lm-sensors

Це upstream-компоненти для графіки, Vulkan, інвентаризації, аудіо, мережі та накопичувачів. Manifest не містить WSM-owned tools, закритих NVIDIA/Intel firmware чи пропрієтарних драйверів. Збірка цих package roots не доводить фізичну сумісність плати H170 або функціональність GTX 1050 Ti.

Кастомне ядро linux-libre-h170 — окремий WSM package з pinned upstream Linux-libre та одним upstream GP107 Nouveau atomic-KMS fix. Воно має власний exact-lock build та окремий Release workflow; його не підмінює звичайний linux-libre у цьому upstream manifest.

## Підпис cache snapshot

Кожний cache snapshot отримує окрему ефемерну пару Guix archive keys, створену на ізольованому GitHub Actions runner:

- приватний ключ використовується лише для підпису NAR у цьому запуску;
- приватний ключ не потрапляє до репозиторію, Actions artifacts, Release чи Pages;
- публічний ключ публікується як signing-key.pub у відповідному Release і на Pages;
- Release містить NAR assets, provenance, input revision, публічний ключ і SHA256SUMS;
- після upload workflow завантажує Release назад і перевіряє кожен checksum.

Ключ змінюється для кожного snapshot. Після оновлення кешу клієнт має перевірити нову пару Release/Pages, а потім авторизувати актуальний публічний ключ. Старий ключ не слід вважати ключем нового snapshot. Це deliberate rotation без постійного owner secret; довіра користувача встановлюється до конкретного опублікованого snapshot, а не до рухомого приватного ключа.

## Підключення клієнта

Після успішного workflow візьми Pages URL та Release tag із summary. Переконайся, що signing-key.pub і provenance у Release відповідають файлам, розгорнутим на Pages. Перевір checksum Release assets. Лише після цього авторизуй актуальний public key:

~~~sh
curl -fsS <PAGES_URL>/signing-key.pub -o signing-key.pub
guix archive --authorize < signing-key.pub
~~~

Далі додай Pages URL до substitute-urls Guix daemon поряд з офіційними серверами. Якщо згодом Pages розгорнуто з новим cache snapshot, повтори перевірку й авторизуй новий ключ.

## Що залишається поза кешем

- WSM-owned wsm-tools і live tools мають окрему ліцензійну metadata review у #367. Це не затримує upstream Free package set.
- NVIDIA GP107 firmware не включається й не перерозповсюджується; #586 залишається окремою правовою межею.
- Compatibility/Nonguix і proprietary NVIDIA packages не входять до Free cache.
- Автентифікація самого WSM channel через Phase B — інший механізм. Цей cache будується з офіційного Guix lock і не представляється як authenticated WSM channel consumption.

## Межі доказів

Успішний cache workflow доводить для конкретного Guix lock і manifest:
- package derivations evaluated і built;
- NAR roots створені та підписані;
- NAR assets опубліковані в Release;
- .narinfo/nix-cache-info розгорнуті в Pages;
- опубліковані файли пройшли read-back SHA-256 перевірку.

Він не доводить:
- фізичний boot на GA-H170-Gaming 3;
- binding Nouveau/i915 або роботу Ethernet, audio, SATA/NVMe чи USB на реальній машині;
- GP107 KMS, 3D, NVK compute, reclocking або firmware loading;
- інсталяцію, розмітку диска, BIOS/UEFI зміну або suspend/resume.

ISO, NAR та інші великі артефакти не комітяться у звичайні Git-гілки.
