# Cuirass: збірка всередині Guix

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **конфігурація описана й перевірена структурно; інстанс не запускався**
- Файли: [специфікації](../ci/cuirass/specs.scm), [image job](../ci/cuirass/images.scm), [фрагмент сервісу](../ci/cuirass/service.scm)

## Роль Cuirass у конвеєрі

Cuirass — Guix-native CI для повторюваного обчислення derivations та їх збірки. Він доповнює GitHub Actions, але не замінює релізне приймання.

| Що доводимо | Механізм |
| --- | --- |
| Guix channel packages та Minimal Live image derivation обчислюються/збираються | Cuirass |
| Образ запускається в BIOS і UEFI | QEMU acceptance у release workflow |
| Інсталятор стартує в завантаженому гості, а його інструменти доступні | серійні докази з QEMU guest |
| Образ проходить повний релізний контракт і може бути опублікований | release gate після перевірки всіх доказів |

Cuirass image job використовує штатний image->job з pinned Guix (gnu ci) для побудови ISO-образу з iso9660-image та конфігурації systems/live-minimal.scm. Це окремий шлях обчислення/build тієї самої конфігурації, але зелений результат не є свідченням завантаження або готовності інсталятора.

## Межі pinning

У job specifications офіційний Guix input має той самий commit, що й channels.lock.scm. WSM input наразі відстежує branch main: його commit змінюється між evaluations. Отже, це rolling CI lane для розробки каналу, а не незмінна пара входів релізу й не доказ того, що конкретна релізна збірка спиралася на той самий WSM commit.

Для релізної відтворюваності треба зберігати точну пару Guix/WSM commit у маніфесті конкретної збірки. Не називати main pinned. Підписаний release/tag не може виводитись лише з rolling jobset.

## Запуск і довіра каналу

**Не реєструвати jobset проти WSM channel, доки не завершено Phase B.** Потрібні owner-controlled .guix-authorizations, signed introduction/history і публічний keyring branch, а споживач має успішно виконати звичайний guix git authenticate. Не вимикати authentication і не створювати фальшиві introduction/fingerprint/key.

Фрагмент хост-сервісу використовує локальний specs.scm, включений у system closure через local-file, і слухає лише localhost:8081. Це конфігураційний приклад для окремого Guix build host; інстанс не реєструвався й не запускався.

## Substitutes: окрема система публікації

Локальний Cuirass scheduler сам по собі **не публікує substitutes іншим машинам**. Параметр fallback? керує поведінкою при невдалому substitute lookup, а не створює публічний cache. Для роздачі результатів потрібен окремо спроєктований та адміністрований механізм, наприклад guix publish із signing key, налаштованим client trust і мережею/ACL, або відповідний Cuirass remote-server/worker deployment.

У цьому репозиторії публікація відкладена до:
- рішення щодо ліцензії пакетів (#367);
- owner-controlled custody і ротації substitute signing key;
- процедури поширення та авторизації ключа на клієнтах;
- приватного/автентифікованого доступу до Cuirass admin UI і publish endpoint.

Не запускати guix publish, не створювати ключі та не оголошувати cache публічним у межах цього change.

## Що Cuirass не доводить

- **Не завантажує образ.** Немає BIOS/UEFI guest execution у цьому job.
- **Не перевіряє інсталятор у гості.** Для цього потрібні маркери та tool-closure report із завантаженої QEMU системи.
- **Не замінює release gate.** Реліз потребує валідованих channel-resolution і build logs, exact ISO digest, чистого serial evidence та BIOS/UEFI acceptance.

## Стан

Структурні тести перевіряють шлях Scheme-модуля, imports, локальне включення service spec та явні trust boundaries. Вони не є runtime-виконанням Cuirass.

**Інстанс не запускався:** у доступному середовищі немає Guix/PostgreSQL host, а WSM Phase B ще не завершена. Наступна перевірка після виконання цих умов: зареєструвати jobset звичайною authentication, створити package та image derivations, побудувати їх у Cuirass, зберегти точну пару commits і лише окремим релізним workflow запускати BIOS/UEFI QEMU acceptance.
