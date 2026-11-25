# Gigabyte GA-H170-Gaming 3

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **зібрано з чужого джерела, не перевірено `wsm-hwcheck`**
- Джерело: [`wsm-os/docs/OWNER-HARDWARE-PROFILE.md`](https://github.com/juv4uk/wsm-os/blob/main/docs/OWNER-HARDWARE-PROFILE.md) (зафіксовано 2026-08-29)
- `evidence.json`: **немає**, і саме тому цей профіль не бере участі в інсталяції

## Чому тут README, а не bundle

Дані нижче — спостереження Windows і WSL, зроблені в іншому проєкті. Вони
корисні, але це **не** доказ у сенсі
[HARDWARE-PROFILE-EVIDENCE.md](../../../../docs/HARDWARE-PROFILE-EVIDENCE.md):
немає `report_id` від `wsm-hwcheck`, немає переліку перевірених функцій, немає
того, що саме не працює.

Вигадати ці поля означало б зробити рівно те, проти чого існує формат. Тому
машина описана тут, а bundle з'явиться після першого прогону на ній.

## Що відомо

| Компонент | Значення | Джерело |
| --- | --- | --- |
| Плата | Gigabyte GA-H170-Gaming 3 | Windows CIM |
| Firmware | AMI BIOS F22e, 2018-03-09, UEFI | Windows CIM |
| CPU | Intel Core i5-6400, Skylake, 4C/4T, без SMT | WSL |
| ISA | AVX, AVX2, FMA, BMI1/2, ADX, AES, POPCNT → **x86-64-v3** | WSL |
| Пам'ять | 16 GiB, 2×8 DDR4-2133 | Windows CIM |
| Графіка | Intel HD 530 + NVIDIA GTX 1050 Ti 4 GiB (Pascal, sm_61), PCI `01:00.0` | Windows + `nvidia-smi` |
| Мережа | Killer E2200 Gigabit Ethernet | Windows CIM |
| Накопичувачі | Kingston SNV2S1000G NVMe 1 TB; Samsung 850 EVO SATA 120 GB; Samsung HD321KJ HDD 320 GB | Windows CIM |

## Що з цього випливає для WSM

**`x86-64-v3` — не припущення, а властивість цієї машини.** Skylake має AVX2,
FMA і BMI2, але не має AVX-512, тож `v4` недосяжний за побудовою. Це
зафіксовано тестом у `tests/test_cpu_isa.py`.

**Дискретна графіка не обов'язкова.** Intel HD 530 тягне робочий стіл через
i915/Mesa без жодного пропрієтарного компонента. NVIDIA — опція, і саме тому
вона живе в профілі Compatibility, а не в Desktop.

**NVMe є, і він один.** Розбиття має це враховувати: `nvme0n1` потребує
суфікса `p` у назвах розділів, що покрито `device_for()` в
`wsm_install/install_steps.py`.

**Два різні накопичувачі SATA.** Інсталятор не повинен обирати ціль
самостійно — тільки явний вибір користувача.

## Чого бракує, щоб це стало профілем

1. Прогін `wsm-hwcheck` на самій машині й отримання `report_id`.
2. Заповнення `verified_functions`: що реально перевірено (графіка, звук,
   мережа, suspend).
3. Список того, що **не** перевірено — обов'язковий і непорожній.
4. `hardware_signature` з реальними PCI-ідентифікаторами.

Перший крок робить `scripts/draft_profile_evidence.py`; решту — людина, яка
сиділа за цією машиною.
