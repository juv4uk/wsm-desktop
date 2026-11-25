# Виконання кроків

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **лише dry-run; реальний запис навмисно вимкнений**
- Код: wsm_install/executor.py
- Тести: tests/test_executor.py

## Поточна межа

execute() приймає планові кроки й друкує preview. За замовчуванням не
запускає команд і повертає кожен крок зі статусом skipped. Передавання
dry_run=False завершується відмовою execute.real-mode-disabled до
будь-якої зовнішньої дії.

Це навмисне обмеження. Злитий перший executor не прив'язував кожен argv до
підтвердженого диска, перевіряв acknowledgement лише один раз і мав verifier,
який не перевіряв фактичну появу partition nodes. Такий код не можна
підключати до графічного інтерфейсу або запускати з root.

## Що потрібно перед реальним виконанням

1. **Immutable target-bound plan.** Один validated Layout має містити точний
   шлях диска, спостережений розмір та partition map; усі destructive argv
   мають бути похідними лише від цього плану. Відхиляти довільні Step
   та команди, які вказують на інший диск або розділ.
2. **Runtime identity revalidation.** Перед кожною destructive дією повторно
   читати block-device major/minor, розмір і зв'язок partitions із цільовим
   диском через sysfs. Збігу імені /dev/... недостатньо.
3. **Per-step authorization.** Кожна destructive дія повинна мати окреме
   підтвердження, що називає конкретний диск і дію; підтвердження не можна
   переносити між кроками або після зміни target identity.
4. **Trusted executable paths.** Усі утиліти, включно з blkid, мають бути
   absolute allow-listed executables у фактичному Guix live closure. Ніякого
   пошуку привілейованих програм через успадкований PATH.
5. **Реальні postconditions.** Перевірка partprobe має підтвердити очікувані
   partition nodes і їхні major/minor; udevadm settle — фактичне завершення
   появи потрібних вузлів; mkfs — filesystem type і label; mount —
   відповідність пристрою, mountpoint і filesystem. Кожний тест має читати
   реальне системне свідчення, а не повертати константне True.

Поки всі ці умови не закриті, єдиний дозволений режим цього модуля — dry-run.

## Відновлення і межі

- **Відкату немає.** Після реального форматування автоматичного rollback не
  існує. Перед майбутнім APPLY потрібен recovery plan після кожного кроку.
- **UUID не використовуються.** Імена /dev/nvme... можуть змінитися після
  перезавантаження; потрібен окремий verified UUID handoff.
- **Guix closure не доведений.** Абсолютні шляхи самі по собі не доводять, що
  executables присутні в locked live image.
- **Немає physical proof.** Жоден реальний диск не використовувався; QEMU та
  synthetic tests не доводять фізичну сумісність.
