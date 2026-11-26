<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

# Інструкції для агентів WSM Desktop

Це точка входу для автоматизованих агентів і людей, які працюють у репозиторії. Цей файл не створює паралельного набору правил: канонічні політики залишаються у відповідних документах та acceptance-контрактах.

## Карта джерел

- [CONTRIBUTING.md](CONTRIBUTING.md) — внесок, тестування, exact-head CI, merge policy та мовна політика.
- [LESSONS-FROM-OMARCHY.md](docs/LESSONS-FROM-OMARCHY.md) — перевірені failure modes із Omarchy та WSM-запобіжники.
- [docs/ECOSYSTEM-PRINCIPLES.md](docs/ECOSYSTEM-PRINCIPLES.md) — критерії когерентності екосистеми: стек, evidence per claim, `fail safely`, антипатерни, Definition of Done.
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — середовище розробки та Guix bring-up.
- [agents/skills/](agents/skills/) — task-specific процедури; для installer/provisioning читайте [installer-lifecycle.md](agents/skills/installer-lifecycle.md).
- [docs/](docs/) — архітектура та прийняті рішення. Зокрема [STATELESS-CONFIGURATION.md](docs/STATELESS-CONFIGURATION.md), [PARTITIONING.md](docs/PARTITIONING.md) і [INSTALLER-HANDOFF.md](docs/INSTALLER-HANDOFF.md) є власниками своїх контрактів.
- [schemas/](schemas/) і відповідні validators — машинно-читані контракти. Не змінюйте їхню версійну семантику мовчки.

Не підтримуйте другу копію списку команд, профілів, станів або acceptance-вимог. Інші документи мають посилатися на канонічного власника.

## Перед багатокроковою роботою

1. Прочитайте CONTRIBUTING.md, пов'язаний issue та відповідний task guide/ADR.
2. Звірте актуальний `main`, відкриті issue/PR і власника вже заявленої роботи; узгодьте одну canonical гілку та один PR на логічний результат.
3. Перевірте точні source refs і попередні напрацювання у власних репозиторіях, коли це доречно. Переносьте код або метод лише після перевірки семантики, API/contract, ліцензії й тестів; не переносіть claims без сирих доказів.
4. Відокремлюйте код, який написано, від того, що реально перевірено. Статичний тест, Guix evaluation/build, QEMU TCG/KVM та фізичне обладнання — різні рівні доказу.
5. Новий тест має ловити конкретну регресію: він має бути червоним без виправлення та зеленим із ним. Згадка імені файла або рядка у source не є поведінковим coverage; тестуйте справжній компонент, а не stub. Деталі й приклади — у CONTRIBUTING та `tests/`.

Детальні правила тестування, звітності, синхронізації та злиття визначає [CONTRIBUTING.md](CONTRIBUTING.md); не копіюйте їх сюди.

## Мова та безпека

Українська — канонічна мова документації й інженерних рішень WSM. Переклади, якщо вони потрібні, зберігаються поруч і не суперечать українському оригіналу.

Не запускайте APPLY, форматування, repartition, `guix system init` чи інші disk-writing дії на фізичному диску під час розробки. Для інсталяційного acceptance використовуйте disposable QEMU images. Не додавайте відомі паролі, секрети або приватні ключі в образи, source чи журнали. Preflight і звичайний hardware report мають залишатися read-only.
