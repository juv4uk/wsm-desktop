;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — цільовий десктопний профіль з KDE Plasma.
;;
;; СТАТУС: не зібрано й не перевірено. У середовищі, де цей файл написано,
;; немає ні Guix, ні QEMU, тому жоден рядок нижче не виконано. Перш ніж
;; вважати цей профіль працездатним, його треба зібрати й завантажити на
;; машині з Guix:
;;
;;     guix system build systems/desktop.scm
;;     guix system vm --no-graphic systems/desktop.scm
;;
;; Назви служб і полів звіряти з посібником тієї ревізії Guix, яку фіксує
;; channels.lock.scm. Якщо поле не збігається — правити тут, а не в
;; документації.
;;
;; Чого тут свідомо немає:
;;   - nonfree firmware і драйверів: вони належать профілю WSM Compatibility
;;     і потребують окремого рішення за docs/ETHICS.md;
;;   - Nonguix: Free-профіль не повинен від нього залежати (ADR 0003);
;;   - автоматичного встановлення: цей файл описує систему, а не інсталятор.

(use-modules (gnu)
             (gnu system locale)
             (wsm systems performance)
             (gnu services desktop)
             (gnu services networking)
             (gnu services sddm)
             (gnu services sound)
             (gnu packages fonts))
;; (gnu packages kde-plasma) не потрібен: пакет plasma приходить через
;; plasma-desktop-service-type, а не через поле packages.

(operating-system
  (host-name "wsm")
  (timezone "Europe/Kyiv")

  ;; Локаль — українська, але з en_US як запасним варіантом: частина
  ;; застосунків досі ламається на не-англійському locale за замовчуванням.
  (locale "uk_UA.utf8")
  (locale-definitions
   (list (locale-definition (name "uk_UA.utf8") (source "uk_UA"))
         (locale-definition (name "en_US.utf8") (source "en_US"))))

  ;; Дві розкладки: латинка для паролів і шляхів, українська для роботи.
  (keyboard-layout (keyboard-layout "us,ua" #:options '("grp:alt_shift_toggle")))

  (bootloader
   (bootloader-configuration
    (bootloader grub-efi-bootloader)
    (targets (list "/boot/efi"))
    (keyboard-layout keyboard-layout)))

  (file-systems
   (cons* (file-system
           (mount-point "/")
           (device (file-system-label "wsm-root"))
           (type "ext4"))
          (file-system
           (mount-point "/boot/efi")
           (device (file-system-label "wsm-efi"))
           (type "vfat"))
          %base-file-systems))

  (users
   (cons* (user-account
           (name "wsm")
           (comment "WSM Desktop")
           (group "users")
           (supplementary-groups '("wheel" "netdev" "audio" "video" "lp"))
           (home-directory "/home/wsm"))
          %base-user-accounts))

  ;; Шрифти з кирилицею — обов'язкові, інакше український інтерфейс
  ;; показується квадратами.
  (packages
   (append (list font-dejavu font-liberation
                 font-google-noto font-google-noto-sans-cjk)
           %base-packages))

  (services
   (append
    ;; Служби, що впливають на затримку: zram, earlyoom, fstrim.
    ;; Кожна пояснена в systems/performance.scm, межі — в docs/PERFORMANCE.md.
    %wsm-performance-services

    (list
     ;; Робоче середовище.
     (service plasma-desktop-service-type)

     ;; Один графічний вхід. GDM із %desktop-services прибираємо нижче,
     ;; інакше два дисплейні менеджери борються за один seat.
     ;; display-server навмисно НЕ задано: у Guix значення "wayland" для
     ;; sddm-service-type відоме як зламане — екран лишається чорним, бо
     ;; greeter не налаштований під wayland. Помилку зафіксовано в Guix
     ;; (bug#68939), а патч bug#70527 змушує службу ігнорувати це значення й
     ;; усе одно використовувати x11. Тримаємо типовий x11, доки служба не
     ;; почне підтримувати wayland по-справжньому.
     (service sddm-service-type (sddm-configuration))

     ;; Звук.
     (service pipewire-service-type
              (pipewire-configuration
               (enable-pulseaudio? #t)))

     ;; Мережа.
     (service network-manager-service-type)
     (service wpa-supplicant-service-type)

     ;; Bluetooth.
     (service bluetooth-service-type
              (bluetooth-configuration
               (auto-enable? #t)))

     ;; Друк: потрібен і мережевий принтер, і локальний USB.
     (service cups-service-type
              (cups-configuration
               (web-interface? #t)
               (default-paper-size "A4")
               (default-printer-options '(("PageSize" . "A4"))))))

    ;; %desktop-services уже включає GDM. Ми його не хочемо, оскільки
    ;; запускаємо SDDM, але решта сервісів GNOME (udisks, polkit, elogind)
    ;; нам потрібна.
    (modify-services %desktop-services
      (delete gdm-service-type)))))

