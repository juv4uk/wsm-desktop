;; SPDX-License-Identifier: GPL-3.0-or-later
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
             (gnu services desktop)
             (gnu services networking)
             (gnu services sddm)
             (gnu services sound)
             (gnu packages fonts)
             (gnu packages kde-plasma))

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
   (append (list font-dejavu font-liberation font-noto font-noto-cjk)
           %base-packages))

  (services
   (append
    (list
     ;; Робоче середовище.
     (service plasma-desktop-service-type)

     ;; Один графічний вхід. GDM із %desktop-services прибираємо нижче,
     ;; інакше два дисплейні менеджери борються за один seat.
     (service sddm-service-type
              (sddm-configuration
               (display-server "wayland")))

     ;; Звук.
     (service pulseaudio-service-type)

     ;; Bluetooth вимкнений за замовчуванням і вмикається користувачем:
     ;; радіо, яке ніхто не просив, — це не «зручність за замовчуванням».
     (service bluetooth-service-type
              (bluetooth-configuration
               (auto-enable? #f))))

    (modify-services %desktop-services
      ;; Рівно один дисплейний менеджер.
      (delete gdm-service-type)

      ;; Мережа через NetworkManager, DNS — від DHCP, без жорстко заданих
      ;; серверів: проєкт не має вбудовувати чужі резолвери.
      (network-manager-service-type
       config => (network-manager-configuration
                  (inherit config)
                  (dns "default"))))))

  (name-service-switch %mdns-host-lookup-nss))
