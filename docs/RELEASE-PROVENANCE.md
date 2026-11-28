# Походження релізних артефактів: provenance-атестації

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **дослідження** — вхідні дані для рішення про політику підпису образів (M6), не рішення
- Дата: 2026-11-26
- Пов'язане: [#405](https://github.com/juv4uk/wsm-desktop/pull/405) (збірка й публікація ISO в CI), [VERIFIED-ARTIFACTS.md](VERIFIED-ARTIFACTS.md) (що вже перевірено), [UPSTREAMS.md](UPSTREAMS.md) (SBOM із `guix graph`), [RELEASE-TAGS.md](RELEASE-TAGS.md) (семантика та цілісність Git-тегів)

## Що це дає

Зараз довіра до нашого ISO тримається на трьох речах: SHA-256 у `SHA256SUMS`, запис у [VERIFIED-ARTIFACTS.md](VERIFIED-ARTIFACTS.md) і те, що людина бачить workflow у GitHub Actions. Це відповідає на питання «файл не зіпсований?», але не на питання «цей файл справді зібрав наш workflow із цього коміту?».

GitHub Actions уміє відповідати на друге: `actions/attest@v4` створює підписану (Sigstore) атестацію, яка прив'язує артефакт до workflow, репозиторію, коміту й події, що його запустила. Це SLSA v1.0 Build Level 2 — рівень, який дає зв'язок «артефакт ↔ інструкції збірки», але не гарантує, що сам артефакт безпечний.

## Як це виглядає в workflow

```yaml
permissions:
  id-token: write        # OIDC-токен для Sigstore-сертифіката
  attestations: write    # зберегти атестацію
  artifact-metadata: write

steps:
  - uses: actions/attest@v4
    with:
      subject-path: build/wsm-desktop-live.iso
```

Перевірка на боці користувача:

```sh
gh attestation verify wsm-desktop-live.iso --repo juv4uk/wsm-desktop
```

Другий режим — атестація SBOM (`sbom-path`), яка приймає SPDX або CycloneDX. Це стикується з тим, що Guix уміє видавати CycloneDX із `guix graph`: provenance каже «хто зібрав», SBOM каже «з чого складається».

## Чого це не дає

- **Не замінює підпис нашим ключем.** Атестація підписана короткоживучим сертифікатом GitHub, а не ключем проєкту. Політика підпису образів у WSM ще не визначена — це окреме рішення M6.
- **Не перевіряє, що артефакт безпечний.** Документація GitHub прямо це каже: атестація лише зв'язує артефакт із джерелом і build instructions.
- **Не працює без перевірки.** Атестація, яку ніхто не перевіряє, не додає безпеки; вона має сенс лише тоді, коли `gh attestation verify` входить у нашу ж інструкцію перевірки.
- **Не для тестових збірок.** Атестувати кожен CI-прогін — це шум; сенс мають лише артефакти, які людина справді запускає.
- **Інфраструктурна залежність.** У публічному репозиторії використовується публічний Sigstore; у приватному — приватний Sigstore GitHub, і для цього потрібен Enterprise Cloud. Для нашого випадку (публічний репозиторій) це не обмеження, але воно стане ним, якщо репозиторій колись закриють.

## Відтворюваність образу — не те саме, що provenance

Provenance відповідає на «хто і з якого коміту це зібрав». Відтворюваність
відповідає на інше: «чи дасть повторна збірка ті самі байти?». Друге — єдине,
що робить опублікований SHA-256 перевірюваним кимось, крім нас.

Що вимагає [reproducible-builds.org](https://reproducible-builds.org/docs/system-images/)
для ISO-образів: свіжий `xorriso`, який поважає `SOURCE_DATE_EPOCH`; передача
`--modification-date`; фіксований `isohybrid --id`; відтворювані initramfs.
Автор `xorriso` додає важливе уточнення: ISO відтворюваний гарантовано лише
**тією ж версією** `xorriso`, `libisofs` і `libisoburn`, тому версії цих
інструментів треба записувати й публікувати разом з образом.

Наш `manifest.json` уже фіксує: коміт джерела, `profile_sha256`, `channel_lock_sha256`,
`locked_guix_channel_commit`, вивід `guix --version` під `time-machine`, SHA-256
образу й команду збірки. Версія `xorriso` прямо не записана, але вона похідна
від зафіксованого коміту каналу — тобто пін каналу і є фіксацією інструментів.
Окреме поле з версіями додало б читабельності, але не додало б доказу.

Корисний орієнтир — `mkosi` (проєкт systemd), який збирає образи через
`systemd-repart` і має для відтворюваності окремі ручки: `SourceDateEpoch=`
(притискає mtime файлів), `Seed=` (детерміновані UUID і PARTUUID замість
випадкових) і `ToolsTree=` (фіксує версії інструментів збірки замість того, щоб
брати їх із хоста). Для WSM `mkosi` не підходить як засіб — він обгортає
`dnf`/`apt`/`pacman`, а наш backend — Guix, — але список того, що ламає
відтворюваність, у нього той самий.

Наскільки це недрібниця: існує окремий проєкт
[`edgelesssys/reproducible-mkosi`](https://github.com/edgelesssys/reproducible-mkosi),
який документує «години налагодження» і десяток upstream-виправлень лише для
того, щоб дві збірки збігалися: поширення `SOURCE_DATE_EPOCH` у `systemd-repart`
і `mcopy`, нормалізація mtime, сортування входу `cpio`, відмова від розширених
PAX-заголовків із atime/ctime. Тобто «Guix уміє відтворювані ISO» — це про
Guix, а не про наш образ: доки ми не зробили двох збірок і не порівняли байти,
ми не знаємо, які з цих пасток у нас увімкнені.

**Чого в нас немає:** жодного прогону, який довів би, що дві збірки дають той
самий SHA-256. Тому WSM не заявляє відтворюваність образу — лише provenance і
цілісність. Твердження «відтворювано» вимагає двох незалежних збірок і
порівняння байтів; доти це `not-tested`, а не властивість.

## Якщо підписувати самим: що змінилося у cosign

Третє питання зі списку нижче — «чи додаємо власний підпис поверх атестації» — має тепер конкретну форму. Стан на 26.11.2026:

- **Cosign v3** (жовтень 2025) увімкнув за замовчуванням новий формат bundle: підписаний матеріал лежить в одному файлі разом із сертифікатом, записом у transparency log та RFC 3161 timestamp. За такого bundle перевірка **не потребує мережі** — достатньо локальної копії trusted root. У v4 старі прапорці приберуть, тож покладатися на старий формат немає сенсу.
- **Keyless підпис прив'язує артефакт до identity, а не до ключа**: сертифікат короткоживучий і виданий за OIDC-токеном (для GitHub Actions — `.../release.yml@refs/heads/main`). Перевірка формулюється як «підписано саме цим workflow», а не «цим ключем». Це знімає потребу зберігати приватний ключ, але додає залежність від стороннього identity provider — рівно та сама інфраструктурна залежність, що вже описана вище для атестацій.
- **Два правила, які легко порушити:** підписувати треба **дайджест**, а не ім'я файлу, і робити це **в тому ж job, де артефакт зібрано** — інакше між збіркою і підписом артефакт можна підмінити.

Що це означає для нас: власний підпис — це не «ще один `.sig`-файл поруч». Якщо ми хочемо, щоб артефакт можна було перевірити офлайн, треба постачати bundle і trusted root, а не сам лише підпис. Це додає до релізу кілька файлів і один крок перевірки — і саме це варто зважити в ADR, а не вирішувати між ділом.

## Офлайн-перевірка GitHub Artifact Attestations

GitHub уже документує офлайн-перевірку атестацій без додаткового Cosign signing step. На машині з мережею треба підготувати три речі: сам release artifact, bundle атестації та snapshot trusted root.

Для конкретного артефакту:

```sh
gh attestation download path/to/wsm-desktop-live.iso \
  --repo juv4uk/wsm-desktop
gh attestation trusted-root > trusted_root.jsonl
```

Потім перенести артефакт, отриманий bundle (файл з digest у назві) та `trusted_root.jsonl` в offline-середовище й виконати:

```sh
gh attestation verify path/to/wsm-desktop-live.iso \
  --repo juv4uk/wsm-desktop \
  --bundle path/to/attestation-bundle.jsonl \
  --custom-trusted-root trusted_root.jsonl \
  --signer-workflow juv4uk/wsm-desktop/.github/workflows/release-minimal-live.yml
```

Для автоматизованої перевірки очікуваного GitHub repository ID використовувати JSON-вивід:

```sh
gh attestation verify path/to/wsm-desktop-live.iso \
  --repo juv4uk/wsm-desktop \
  --bundle path/to/attestation-bundle.jsonl \
  --custom-trusted-root trusted_root.jsonl \
  --signer-workflow juv4uk/wsm-desktop/.github/workflows/release-minimal-live.yml \
  --format json \
  --jq '.[].verificationResult.signature.certificate.sourceRepositoryIdentifier'
```

Числовий ID треба заздалегідь отримати з довіреного онлайн-джерела (`gh api repos/juv4uk/wsm-desktop --jq .id`) і порівняти з кожним ID у результаті. Це важливо, бо офлайн-перевірка за `--repo owner/name` звіряє підписану назву, але не може виявити подальше перейменування репозиторію або повторне використання старої назви.

### Межі trust-root snapshot

- Snapshot, отриманий через `gh attestation trusted-root`, не має вбудованого строку завершення, але його слід оновлювати щоразу перед імпортом нового набору підписаних матеріалів.
- Ключі Sigstore можуть ротуватися кілька разів на рік. Старий snapshot не дає дізнатися про відкликання ключа після його створення; це властиве обмеження офлайн-моделі, а не помилка команди.
- Для майбутнього WSM release workflow треба окремо вирішити, чи публікувати bundle та snapshot як release assets. Поточний workflow перевіряє атестацію онлайн до публікації, але **ще не обіцяє повний offline-verification kit**.
- Наявність bundle не замінює перевірку точного signer workflow, repository ID, source ref і digest артефакту.

### Стан Cosign

Станом на 26.11.2026 upstream GitHub Releases показує Cosign 3.1.4 як актуальний випуск 3.1.x. У 3.1.3 було виправлено verification bypass через неочікуваний public key у legacy bundle. Лінійка 3.1.x за замовчуванням створює стандартизований новий bundle format і продовжує читати обидва формати. Тому, якщо M6 колись обере Cosign, WSM має вимагати новий bundle format і відхиляти legacy bundles у своїй policy; не покладатися на auto-detection як на security policy.

Джерела:
- [GitHub Docs — verifying attestations offline](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/verify-attestations-offline)
- [Cosign releases — new bundle default і security fix для legacy bundle](https://github.com/sigstore/cosign/releases)

Цей розділ фіксує доступний механізм і його обмеження. Він не ратифікує M6, не додає Cosign як залежність і не змінює набір release assets.

## Що з цим робити

Нічого не змінюємо в цьому документі: це вхідні дані. Рішення про provenance і підпис оформлюється окремим ADR разом із політикою підпису образів (M6), і в ньому має бути три речі:

1. які саме артефакти атестуються (релізний ISO — так, щоденні тестові збірки — ні);
2. чи входить `gh attestation verify` в інструкцію перевірки поруч із `SHA256SUMS`;
3. чи додаємо ми власний підпис поверх атестації, чи поки покладаємося на неї — і якщо додаємо, то cosign-ом keyless чи власним ключем, і чи постачаємо bundle з trusted root для офлайн-перевірки.

Джерела: [mkosi: SourceDateEpoch, Seed, ToolsTree](https://github.com/systemd/mkosi/blob/main/mkosi/resources/man/mkosi.1.md), [reproducible-mkosi: перелік upstream-виправлень](https://github.com/edgelesssys/reproducible-mkosi), [reproducible-builds.org — system images](https://reproducible-builds.org/docs/system-images/), [xorriso: reproducibility залежить від версії інструментів](https://lists.reproducible-builds.org/pipermail/rb-general/2025-April/003728.html), [GitHub Docs — artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations), [actions/attest](https://github.com/actions/attest/), [gh attestation verify](https://cli.github.com/manual/gh_attestation_verify), [Sigstore: cosign v3 і новий bundle](https://blog.sigstore.dev/cosign-3-0-available/), [cosign: офлайн-перевірка bundle](https://github.com/sigstore/cosign), [GitLab: keyless-підпис артефактів](https://docs.gitlab.com/ci/yaml/signing_examples/).
