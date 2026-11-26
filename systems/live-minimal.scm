;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — мінімальний live-образ для встановлення на слабке залізо.
;;
;; СТАТУС: не зібрано й не перевірено (у середовищі написання немає Guix).
;;
;; Навіщо окремий образ, а не «повний, але з вимкненим KDE»:
;;
;; Повний live тягне Plasma, SDDM і Qt — це сотні мегабайт пам'яті ще до того,
;; як інсталятор почне працювати. На машині з 2 GB це різниця між
;; «встановлюється» і «не встановлюється», а залізоорієнтованість, яка вимагає
;; достатньо заліза, — не залізоорієнтованість.
;;
;; Тут немає: графічного середовища, дисплейного менеджера, звуку, друку,
;; Bluetooth. Є: консоль на ttyS0/tty1, мережа, WSM CLI/TUI та вхід wsm на tty2.
;;
;; Встановлення веде `wsm-install` (CLI). Calamares сюди не входить навмисно:
;; він потребує Qt, а вся суть цього образу — обійтися без нього.

(use-modules (gnu)
             (gnu system locale)
             (gnu services)
             (gnu services base)
             (gnu services networking)
             (gnu services shepherd)
             (gnu system nss)
             (wsm packages wsm))

;; Маркер готовності — той самий контракт, що в повному live-образі.
;; Приймання вимагає WSM_LIVE_READY у послідовній консолі, і мінімальний образ
;; не має бути винятком: інакше він «завантажується» без доказів.
(define wsm-live-ready-marker
  (simple-service 'wsm-live-ready shepherd-root-service-type
    (list (shepherd-service
           (documentation "Announce on the serial console that the live system is up.")
           (provision '(wsm-live-ready))
           (requirement '(user-processes))
           (respawn? #f)
           (start #~(lambda ()
                      (catch #t
                        (lambda ()
                          (call-with-output-file "/dev/console"
                            (lambda (port)
                              (display "WSM_LIVE_READY" port)
                              (newline port)
                              (force-output port))))
                        (lambda _ #f))
                      #t))
           (stop #~(const #t))))))

(operating-system
  (host-name "wsm-live-minimal")
  (timezone "Europe/Kyiv")
  ;; Українська — основна локаль live-системи; Guix додає її до locale data.
  (locale "uk_UA.utf8")
  ;; US лишається для шляхів і паролів; Alt+Shift перемикає US/UA.
  (keyboard-layout
   (keyboard-layout "us,ua" #:options '("grp:alt_shift_toggle")))

  (bootloader
   (bootloader-configuration
    (bootloader grub-efi-bootloader)
    (targets '("/boot/efi"))
    (keyboard-layout keyboard-layout)))

  (file-systems
   (cons* (file-system
            (mount-point "/")
            (device (file-system-label "wsm-live-root"))
            (type "ext4"))
          %base-file-systems))

  (users (cons* (user-account
                 (name "wsm")
                 (comment "WSM live user")
                 (group "users")
                 (supplementary-groups '("wheel" "netdev" "lp"))
                 (home-directory "/home/wsm"))
                %base-user-accounts))

  ;; Рівно те, що потрібно, щоб дійти до консолі й запустити інсталятор.
  (packages (append (list wsm-tools)
                    %base-packages))

  (services
   (modify-services
    (append (list
             wsm-live-ready-marker
             ;; NetworkManager uses its internal DHCP client by default.
             ;; Do not start a second system-wide DHCP daemon beside it.
             (service network-manager-service-type)
             (service wpa-supplicant-service-type))
            %base-services)
    ;; %base-services уже має один console-font-service для tty1–tty6.
    ;; Змінюємо шрифт tty2 у ньому, не додаючи дубль Shepherd service.
    (console-font-service-type config =>
      (map (lambda (tty+font)
             (if (string=? (car tty+font) "tty2")
                 (cons "tty2" "LatGrkCyr-8x16")
                 tty+font))
           config))
    ;; tty1 і serial лишаються для boot logs; live-сесія доступна на tty2.
    (mingetty-service-type config =>
      (if (string=? (mingetty-configuration-tty config) "tty2")
          (mingetty-configuration
           (inherit config)
           (auto-login "wsm"))
          config))))

  (kernel-arguments '("console=ttyS0,115200" "console=tty1")))
