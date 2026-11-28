;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — маніфест публікації для H170.
;;
;; Один файл, який каже: «ось набір пакетів, який потрібен машині власника».
;; Його читає людина перед відправкою, і його читає
;; .github/workflows/package-archives.yml, коли запускають один dispatch.
;; Раніше цей набір набирали руками в поле `packages` — такий список неможливо
;; ані перевірити очима, ані порівняти з тим, що машина справді потребує.
;;
;; Машина: Gigabyte GA-H170-Gaming 3 (BIOS F22e, UEFI), Intel Core i5-6400
;; (Skylake), NVIDIA GTX 1050 Ti (GP107, 10de:1c82). Ідентичність береться з
;; drivers/profiles/h170-free.json і docs/hardware/OWNER-HARDWARE-REFERENCE.md.
;;
;; ЩО ТУТ Є І ЧОМУ САМЕ ЦЕ. Набір виведено з systems/h170.scm — єдиного опису
;; цієї машини в репозиторії: він називає ядро (linux-libre) і відкритий
;; GPU-стек (mesa). Третій запис — wsm-tools, інсталятор. Він не з'являється в
;; operating-system, бо це інструмент, який ставлять на машину, а не частина її
;; closure, але публікація без нього не має сенсу: саме він дає wsm-install і
;; wsm-hwcheck. Більше тут нічого немає навмисно —
;; tests/test_system_profiles.py порівнює цей список із тим, що systems/h170.scm
;; справді називає, тому зайвий пакет це червоний тест, а не «про запас».
;;
;; ЧОГО ТУТ НЕМАЄ:
;;   * nonfree firmware і пропрієтарного NVIDIA-драйвера — Free-канал їх не
;;     розв'яже взагалі, а #514 це забороняє (заголовок systems/h170.scm);
;;   * Nonguix — ADR 0003;
;;   * підписного ключа, secrets і всього, що стосується substitute-сервера: це
;;     substitutes.yml, не цей файл. Тут немає нічого, крім переліку пакетів.
;;
;; ВІДНОШЕННЯ ДО drivers/profiles/h170-free-packages.scm. Той файл — набір для
;; build-evidence і Cuirass: він upstream-only (його збирають без -L ., лише з
;; офіційного каналу), тому wsm-tools там навмисно відсутній, і він покриває
;; ширший перелік діагностичних інструментів (vulkan-tools, pciutils, ethtool
;; тощо), які systems/h170.scm не називає. Цей файл — те, що публікується для
;; машини: рівно те, що вона потребує для роботи, включно з інсталятором.
;; Два різні контракти з двома різними споживачами, тому два файли, а не один
;; з розгалуженням.
;;
;; ФОРМАТ. `specifications->manifest` — той самий тип, що й у
;; h170-free-packages.scm, тому файл можна віддати Guix напряму:
;;
;;     guix time-machine -C channels.lock.scm -L . -- \
;;       build --manifest=drivers/profiles/h170-publication-packages.scm --no-grafts
;;
;; Кожен запис має рівно один рядок-обґрунтування у формі
;;
;;     <ім'я> <- <файл>:<рядок>
;;
;; і tests/test_system_profiles.py перевіряє, що вказаний рядок справді називає
;; це ім'я. Посилання не може відірватися від джерела непоміченим.
;;
;; СТАТУС: НЕ ЗІБРАНО Й НЕ ОЦІНЕНО. У середовищі, де цей файл написано, немає
;; `guix`, тому жоден запис не перевірено на pinned-ревізії channels.lock.scm.
;; Це список того, що треба зібрати, а не доказ, що воно збирається.

(specifications->manifest
 '(
   ;; Інсталятор: wsm-install і wsm-hwcheck на цільовій машині; wsm-tools <- wsm/packages/wsm.scm:31
   "wsm-tools"

   ;; Ядро: i915, nouveau, alx, nvme, ahci, snd_hda_intel без власного .config; linux-libre <- systems/h170.scm:115
   "linux-libre"

   ;; Відкритий GPU-стек GP107: nouveau_dri.so і libvulkan_nouveau.so; mesa <- systems/h170.scm:152
   "mesa"))
