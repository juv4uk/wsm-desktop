# Пакети WSM та substitute cache

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Власник дозволив публікацію власних WSM package outputs 2026-11-28.
- Спільний явний tag namespace: `packages-*`.
- H170 Free стартовий набір: `wsm-tools`, `linux-libre`, `mesa`.
- GP107 NVIDIA firmware та proprietary NVIDIA 580.x до цього набору не входять.
- Фактична збірка, NAR export, Release assets і Pages deployment мають бути підтверджені окремими Actions runs.

## Два різні способи розповсюдження

### Package archives

`.github/workflows/package-archives.yml` запускається через `workflow_dispatch`
або push тега `packages-*`. Для першої цілі за замовчуванням збирається:

- `wsm-tools` — локальний WSM пакет із `wsm/packages/wsm.scm`;
- `linux-libre` — upstream пакет із pinned офіційного Guix;
- `mesa` — upstream пакет із pinned офіційного Guix.

Локальний пакет резолвиться явним Guile expression:

```sh
guix time-machine -C channels.lock.scm -- build -L . \
  -e '(@ (wsm packages wsm) wsm-tools)' --no-grafts
```

Інші пакети резолвляться за іменем у тому самому locked Guix. Workflow експортує вибрані store paths у `.nar`, формує SHA-256 та зберігає їх як Actions artifact із 30-денним retention. За окремим `workflow_dispatch` цей archive можна прикріпити до вже створеного **draft** release. Tag-trigger створює artifact, але сам по собі не робить його Guix substitute і не підписує NAR.

### Signed substitute cache

`.github/workflows/substitutes.yml` також приймає `workflow_dispatch` або тег
`packages-*`. Він збирає той самий H170 Free baseline набір, запускає
`guix publish`, витягує фактичні NAR-архіви в локальний cache та публікує:

- стиснені NAR як assets GitHub Release `substitutes`;
- підписані narinfo, `nix-cache-info` і `signing-key.pub` через GitHub Pages.

Публікація працює тільки із секретом Actions `GUIX_SIGNING_KEY`. Workflow
відмовляється продовжувати без нього; непідписаний substitute cache не
створюється. Приватний ключ генерується й зберігається власником, ніколи не
комітиться до репозиторію або не виводиться в лог.

На машині, де встановлено Guix:

```sh
sudo guix archive --generate-key
gh secret set GUIX_SIGNING_KEY --repo juv4uk/wsm-desktop \
  < /etc/guix/signing-key.sec
```

## Дві окремі довіри

1. Guix narinfo підписується cache key. Користувач має явно додати відповідний
   публічний ключ до trust configuration свого Guix client.
2. `guix git authenticate` перевіряє історію самого WSM channel. У WSM channel
   поки немає owner-signed introduction, `.guix-authorizations` і keyring
   branch. Поточні build workflows беруть WSM module з exact GitHub checkout
   commit і використовують окремий pinned official Guix lock; вони не
   заявляють, що WSM channel authenticated.

## Ліцензія та апаратні межі

Правовласник дозволив публікацію власних WSM package outputs у WSM-owned cache.
Guix metadata для WSM-owned `wsm-tools` та live helper packages посилається
на фактичну ВОЛЬНІСТЬ через `file://LICENSE`, а не помилково заявляє GPL-3+.
Це вузький дозвіл на власні outputs; він не є твердженням про OSI або GNU FSDG
і не означає, що WSM ліцензію прийнято upstream GNU Guix.

Початковий набір — Free baseline для x86_64 з upstream Linux-libre/Mesa та
WSM hardware tools. Він **ще не є перевіреним профілем GA-H170-Gaming 3** і
не доводить успішний graphics runtime на цій машині. Профіль сумісності
з'явиться лише після native Linux hardware report та окремих функціональних
доказів.

NVIDIA GP107 firmware і proprietary NVIDIA 580.x не включаються та не
перерозповсюджуються цими workflow. Вони мають окремі third-party license,
firmware provenance та runtime acceptance вимоги; власний дозвіл на WSM
outputs на них не поширюється. Free та Compatibility boot paths не
змішуються.

## Статус

PR #775 увімкнув archive workflow, #778 додав явний tag-trigger для нього,
а #771 увімкнув substitute workflow. Ця гілка усуває помилки локального
package lookup і NAR cache warm-up та синхронізує обидва workflows під один
H170 Free baseline.

До успішного exact-head CI та першого успішного Actions run жоден NAR не
вважається зібраним або опублікованим. До read-back перевірки Release assets
і Pages metadata не можна заявляти, що cache доступний користувачам.
