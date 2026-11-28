;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — H170: система під конкретну машину власника.
;;
;; Машина: Gigabyte GA-H170-Gaming 3 (BIOS F22e, UEFI), Intel Core i5-6400
;; (Skylake), Intel HD Graphics 530, NVIDIA GTX 1050 Ti (Pascal, GP107,
;; 10de:1c82), Killer E2200 (alx), Realtek HDA, Samsung SATA + Kingston NVMe.
;; Джерела ідентичності: docs/hardware/OWNER-HARDWARE-REFERENCE.md,
;; docs/hardware/H170-FIRMWARE-MATRIX.md, drivers/profiles/h170-free.json,
;; issue #514.
;;
;; ===========================================================================
;; СТАТУС: NOT VERIFIED ON HARDWARE — не перевірено на залізі.
;; ===========================================================================
;;
;; Це не сертифікований, не випробуваний і навіть не оцінений профіль.
;; Прочитайте це до того, як довіряти будь-чому нижче.
;;
;; Для цієї машини немає native Linux звіту `wsm-hwcheck`, немає каталогу
;; profiles/hardware/<vendor>/<model>/ — profiles/hardware/README.md прямо
;; забороняє створювати його без такого звіту — і немає жодного
;; функціонального тесту з цього заліза. Усі наявні докази є або
;; Windows/WSL-спостереженням, або статичним source/license аудитом. Жодне з них
;; не є доказом того, що Linux працює на цій платі.
;;
;; Тут не виконано навіть оцінки виразу: у середовищі, де цей файл написано,
;; немає `guix`. Тому невідомо навіть, чи розв'язується він на зафіксованій
;; ревізії каналу (channels.lock.scm). Не читайте цей файл як «збирається»: це
;; гіпотеза, записана в Scheme, а не результат.
;;
;; ЩО ЛИШАЄТЬСЯ НЕПЕРЕВІРЕНИМ до появи native звіту:
;;   - оцінка й збірка системи, ядра, Mesa та initrd на channels.lock.scm;
;;   - завантаження через GRUB/UEFI саме на цій платі (Secure Boot — unknown);
;;   - прив'язка модулів i915, nouveau, alx, snd_hda_intel, nvme, ahci до
;;     фактичних PCI ID саме на H170: Windows PCI ID не є Linux binding;
;;   - будь-яка робота GPU: базовий KMS, OpenGL, Vulkan/NVK enumeration;
;;   - firmware: чи завантажується те, що BIOS уже дає, і чого бракує (нижче);
;;   - мережа, звук, SATA/NVMe I/O, USB, suspend/resume.
;;
;; ЧОГО ТУТ СВІДОМО НЕМАЄ:
;;   - nonfree firmware. linux-firmware живе лише в Compatibility-профілі
;;     (systems/compatibility.scm) з окремим lock-ом, і Free-канал його не
;;     розв'яже взагалі: додавання зробило б цей файл неоцінюваним, а не
;;     «повнішим». Для цієї плати жодного вільного firmware-пакета не потрібно
;;     (alx, HDA, AHCI, NVMe, xHCI, i915 і nouveau працюють без зовнішніх blob-ів
;;     — issue #514), а той firmware, якого справді бракує (GP107 FECS/GPCCS,
;;     i915 DMC, Intel OS microcode), є nonfree і тому лишається поза цим файлом;
;;   - proprietary NVIDIA. Стан відкритого драйвера для GP107 не вирішений
;;     (#512), жоден драйвер не заявлено робочим;
;;   - systems/wsm-gp107.modconfig: він належить Compatibility ISO і навмисно
;;     вимикає nouveau/i915 (drivers/profiles/h170-free.json:37);
;;   - жодного пакета, чия ліцензія не представлена в LICENSES/ або REUSE.toml
;;     (#367): додати такий пакет означало б вирішити ліцензійне питання мовчки.
;;
;; ЩО ЦЕЙ ФАЙЛ РОБИТЬ. Він виражає один раз те, що потрібно саме цій платі,
;; поверх systems/desktop.scm, щоб після появи native звіту профіль і образ
;; збиралися з цього опису, а не складалися руками.
;;
;; КОЛИ З'ЯВИТЬСЯ NATIVE ЗВІТ, цей файл не замінює той шлях: спершу
;; `python3 -m wsm_hwcheck` на самій машині, далі
;; profiles/hardware/gigabyte/ga-h170-gaming3/profile.scm на основі
;; profiles/hardware/template.scm і evidence bundle за
;; docs/HARDWARE-PROFILE-EVIDENCE.md. Цей файл лише зменшує обсяг ручної роботи,
;; коли звіт з'явиться.
;;
;; ОЦІНКА (коли є Guix):
;;   guix time-machine -C channels.lock.scm -L . -- system -L . \
;;     build systems/h170.scm --dry-run
;;
;; ДОКАЗИ ІМЕН — перевіряє tests/test_system_profiles.py.
;; Формат: `evidence: <ім'я> <- <файл>:<рядок>[, ...]`. Рядок вважається
;; доказом лише тоді, коли у вказаному місці справді згадано це ім'я, тому
;; посилання не може відірватися від джерела непоміченим.
;;
;; Чесне обмеження цього доказу: перевірити імена на самій зафіксованій ревізії
;; Guix (4e5195be20d9b124df8a8bb69213412236e4668e) у середовищі написання було
;; неможливо — немає ні `guix`, ні доступу до джерела Guix. Тому кожне ім'я
;; підкріплене тим, що репозиторій уже вживає його у зібраному або
;; задокументованому контексті. Перед першою реальною оцінкою ці імена треба
;; перевірити на pinned commit; доки цього не зроблено, доказ є
;; repo-level, а не pinned-commit-level.
;;
;;   evidence: linux-libre <- profiles/hardware/template.scm:41, systems/live.scm:23
;;   evidence: mesa <- docs/VERIFIED-ARTIFACTS.md:114, docs/LIVE-ISO.md:60, systems/live-compat.scm:191
;;
;; Налаштування, специфічні для цієї плати, і їхні джерела:
;;   evidence-config: nvme <- systems/wsm-gp107.modconfig:7
;;   evidence-config: nouveau.atomic=0 <- drivers/profiles/h170-free.json:396

(use-modules (gnu)
             (gnu packages linux)
             (gnu packages gl))

;; desktop.scm — вираз, а не модуль, тому його саме завантажують. Шлях
;; будується від current-filename, щоб результат не залежав від поточної
;; директорії (той самий прийом, що в systems/live.scm).
(define base-os
  (load (string-append (dirname (current-filename)) "/desktop.scm")))

(operating-system
  (inherit base-os)

  ;; Машина одна й названа: це не «десктоп взагалі», а H170.
  (host-name "wsm-h170")

  ;; Ядро. linux-libre — те саме ім'я, яке репозиторій уже вживає
  ;; (profiles/hardware/template.scm:41, systems/live.scm:23).
  ;;
  ;; Своєї конфігурації ядра тут навмисно НЕМАЄ. За зафіксованою ревізією
  ;; типовий x86_64-конфіг linux-libre 7.3.5 уже вмикає i915, nouveau, alx,
  ;; snd_hda_intel з кодеком Realtek, SATA_AHCI, NVMe і xHCI
  ;; (drivers/profiles/h170-free.json:37), і саме цей конфіг називає Free-профіль
  ;; цієї плати. Власний .config без збірки був би зміною без доказу, а «не
  ;; вимикати загальні підсистеми ядра без доказу» — пряма вимога #514.
  (kernel linux-libre)

  ;; initrd. На цій машині є Kingston NVMe (пристрій kingston-nv2 у
  ;; drivers/profiles/h170-free.json), а типовий список модулів Guix, за моїм
  ;; знанням, nvme не містить — перевірити це на pinned commit я не міг (немає
  ;; Guix), тому твердження лишається неперевіреним. Якщо корінь опиниться на
  ;; NVMe, без цього модуля ядро не знайде корінь, тому модуль названо явно.
  ;; Беремо успадкований список, а не %base-initrd-modules: так значення
  ;; лишається тим, що реально прийшло з desktop.scm, і жодна друга копія
  ;; типового списку не розходиться з Guix.
  (initrd-modules
   (cons* "nvme" (operating-system-initrd-modules base-os)))

  ;; Аргументи ядра. Один, і в нього є причина в репозиторії, а не «на всяк
  ;; випадок»: зафіксоване ядро 7.3.5 старше за виправлення NULL dereference у
  ;; drm_atomic_commit для GP107 (mainline ed7fb901fce3, 2026-11-25), і
  ;; документований обхід — nouveau.atomic=0
  ;; (drivers/profiles/h170-free.json:388-389).
  ;;
  ;; Це обхід, а не виправлення, і на H170 він не перевірений: жодного
  ;; завантаження не було. Коли буде зафіксовано ядро на виправленні або після
  ;; нього, цей рядок треба прибрати, а не тримати «про всяк випадок».
  ;; `operating-system-kernel-arguments` takes (os root-device #:key version) at the
  ;; pinned commit, so the accessor cannot be called with the base OS alone — the
  ;; locked evaluation refused it with "Wrong number of arguments". The inherited
  ;; arguments are read from the base record directly and the workaround is appended.
  (kernel-arguments
   (append (operating-system-kernel-arguments
            base-os (operating-system-root-device base-os))
           '("nouveau.atomic=0")))

  ;; Відкритий GPU-стек для GP107 — Mesa. У цьому каналі Mesa 26.2.6
  ;; збирається з -Dvulkan-drivers=…,nouveau (тобто з NVK), і саме Mesa дає і
  ;; nouveau_dri.so, і libvulkan_nouveau.so у вільному ISO
  ;; (docs/LIVE-ISO.md:60, docs/VERIFIED-ARTIFACTS.md:114). Ім'я mesa репозиторій
  ;; уже вживає як ім'я пакета (systems/live-compat.scm:191).
  ;;
  ;; Чого це НЕ означає: що GR 3D/compute на GP107 працює. Без NVIDIA-signed
  ;; FECS/GPCCS firmware рушій GR не ініціалізується (docs/drivers/PROFILES.md),
  ;; а такого firmware у Free-профілі немає. Базовий KMS теж не перевірений.
  ;; Пропрієтарний шлях свідомо не додано: це Compatibility, окремий продукт.
  (packages
   (cons* mesa
          (operating-system-packages base-os))))
