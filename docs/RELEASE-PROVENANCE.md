# Походження релізних артефактів: provenance-атестації

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **дослідження** — вхідні дані для рішення про політику підпису образів (M6), не рішення
- Дата: 2026-11-26
- Пов'язане: [#405](https://github.com/juv4uk/wsm-desktop/pull/405) (збірка й публікація ISO в CI), [VERIFIED-ARTIFACTS.md](VERIFIED-ARTIFACTS.md) (що вже перевірено), [UPSTREAMS.md](UPSTREAMS.md) (SBOM із `guix graph`)

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

**Чого в нас немає:** жодного прогону, який довів би, що дві збірки дають той
самий SHA-256. Тому WSM не заявляє відтворюваність образу — лише provenance і
цілісність. Твердження «відтворювано» вимагає двох незалежних збірок і
порівняння байтів; доти це `not-tested`, а не властивість.

## Що з цим робити

Нічого не змінюємо в цьому документі: це вхідні дані. Рішення про provenance і підпис оформлюється окремим ADR разом із політикою підпису образів (M6), і в ньому має бути три речі:

1. які саме артефакти атестуються (релізний ISO — так, щоденні тестові збірки — ні);
2. чи входить `gh attestation verify` в інструкцію перевірки поруч із `SHA256SUMS`;
3. чи додаємо ми власний підпис поверх атестації, чи поки покладаємося на неї.

Джерела: [reproducible-builds.org — system images](https://reproducible-builds.org/docs/system-images/), [xorriso: reproducibility залежить від версії інструментів](https://lists.reproducible-builds.org/pipermail/rb-general/2025-April/003728.html), [GitHub Docs — artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations), [actions/attest](https://github.com/actions/attest/), [gh attestation verify](https://cli.github.com/manual/gh_attestation_verify).
