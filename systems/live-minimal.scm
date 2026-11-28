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

;; DHCP тут не потрібен окремою службою: NetworkManager має власний DHCP-клієнт
;; і керує адресами сам. Окремий клієнт лише боровся б із ним за інтерфейс.
;;
;; Історична довідка: раніше тут стояв dhcp-client-service-type. ISC DHCP
;; досяг end-of-life у 2022, службу спершу позначили застарілою (2025), а потім
;; видалили зовсім. У зафіксованому каналі її вже немає, тому збірка падала з
;; «dhcp-client-service-type: unbound variable» — саме це й показав build.log
;; першої невдалої збірки образу.
;;
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

;; Маркер інсталятора. Готовність системи й робочий інсталятор — різні факти:
;; образ може завантажитись і показати WSM_LIVE_READY, не маючи в closure ні
;; wsm-install, ні його залежностей. Саме так сталось із попереднім носієм, де
;; трьох frontend-ів просто не було.
;;
;; Служба запускає entrypoint і друкує WSM_INSTALLER_OK лише після успішного
;; імпорту. Це не доказ, що TUI малюється: для цього потрібен термінал. Це
;; доказ, що образ містить інсталятор і що він стартує.
(define wsm-installer-selfcheck
  (simple-service 'wsm-installer-selfcheck shepherd-root-service-type
    (list (shepherd-service
           (documentation "Run the installer entrypoint once and report the result on the console.")
           (provision '(wsm-installer-selfcheck))
           (requirement '(user-processes))
           (respawn? #f)
           (start #~(lambda ()
                      ;; The wrapper runs `exec python3`, so the daemon's PATH
                      ;; decides whether the installer can start at all. shepherd
                      ;; does not guarantee the system profile on PATH, and a
                      ;; missing python3 would look like a broken installer.
                      (define (announce text)
                        (catch #t
                          (lambda ()
                            (call-with-output-file "/dev/console"
                              (lambda (port)
                                (display text port)
                                (newline port)
                                (force-output port))))
                          (lambda _ #f)))
                      ;; Two proofs, because they fail differently.
                      ;;
                      ;; `--help` runs the real wrapper and entrypoint, but it
                      ;; never touches jsonschema, the schemas or the planner:
                      ;; an image missing a propagated input would still print
                      ;; help and look healthy.
                      ;;
                      ;; The import check covers exactly that, and nothing else.
                      ;; Neither alone is enough; both together are what a real
                      ;; run needs.
                      (define (ok? . command)
                        (catch #t
                          (lambda () (zero? (apply system* command)))
                          (lambda _ #f)))
                      (cond
                       ((not (ok? "/run/current-system/profile/bin/wsm-install" "--help"))
                        (announce "WSM_INSTALLER_FAIL:exit"))
                       ((not (ok? "/run/current-system/profile/bin/python3" "-c"
                                   (string-append
                                    "import jsonschema, wsm_install.cli, "
                                    "wsm_install.classification, wsm_install.partition, "
                                    "wsm_install.profile")))
                        (announce "WSM_INSTALLER_FAIL:imports"))
                       (else (announce "WSM_INSTALLER_OK")))
                      #t))
           (stop #~(const #t))))))

;; Маркер tool closure (#645). Завантаження доводить, що система стартувала;
;; воно не доводить, що інструменти, які запускатиме інсталятор, існують у цій
;; системі й є виконуваними. Перевірка каталогу на хості цього не доводить:
;; каталог — не завантажена система.
;;
;; Служба запускає wsm_install.tool_closure з того самого образу, що містить
;; інсталятор, і друкує по рядку на кожен allowlisted інструмент у
;; /dev/console. Перевірка read-only: stat і access, без mount, без розділів,
;; без запису на носій — гість не чіпає нічого, крім власного образу.
;;
;; Порядок навмисний: спершу готовність системи, потім інсталятор, і лише потім
;; те, що інсталятор збирається запускати.
(define wsm-tool-closure-probe
  (simple-service 'wsm-tool-closure shepherd-root-service-type
    (list (shepherd-service
           (documentation "Report on the serial console whether the installer tools exist here.")
           (provision '(wsm-tool-closure))
           (requirement '(wsm-live-ready wsm-installer-selfcheck))
           (respawn? #f)
           (start #~(lambda ()
                      (catch #t
                        (lambda ()
                          ;; Той самий python3 і той самий wsm_install, що й у
                          ;; selfcheck інсталятора: перевірка мусить говорити про
                          ;; образ, а не про щось інше на PATH.
                          (system* "/run/current-system/profile/bin/python3" "-m"
                                   "wsm_install.tool_closure"
                                   "--console" "/dev/console"
                                   "--prefix" "/run/current-system/profile/bin"
                                   "--prefix" "/run/current-system/profile/sbin"))
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
             wsm-installer-selfcheck
             wsm-tool-closure-probe
             wsm-live-ready-marker
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

  ;; Linux routes /dev/console to the last console= entry. Keep serial last:
  ;; boot smoke captures ttyS0, while kernel output still reaches tty1 as well.
  (kernel-arguments '("console=tty1" "console=ttyS0,115200")))
