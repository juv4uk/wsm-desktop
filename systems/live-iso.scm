;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — перший перевірений завантажувальний live ISO з KDE Plasma.
;;
;; Цей файл відповідає образу, який реально зібрано й завантажено в QEMU
;; 25 листопада 2026 року. Збірка (у ізольованому Guix store):
;;
;;     guix system image -t uncompressed-iso9660 systems/live-iso.scm
;;
;; Чому uncompressed-iso9660: звичайний --image-type=iso9660 додає zisofs
;; level=9 і на цій машині стискався понад 35 хвилин. Нестиснений образ
;; більший (7,73 GiB), але складається швидко й Ventoy читає його нормально.
;;
;; Що є: KDE Plasma, SDDM із автологіном, NetworkManager + WPA supplicant,
;; наші власні wsm-hwcheck/wsm-install як preflight/dry-run launcher.
;;
;; Чого НЕМАЄ: запису на диск (REALIZE/APPLY з docs/INSTALLER-HANDOFF.md),
;; пропрієтарного firmware чи Nonguix, повної підтримки драйверів на
;; реальному залізі. Це live-попередній перегляд, не інсталятор усього
;; дистрибутива.

(use-modules (gnu)
             (gnu services shepherd)
             (gnu packages python)
             (gnu packages python-xyz)
             (gnu packages screen)
             (guix build-system trivial)
             (guix gexp)
             ((guix licenses) #:prefix license:)
             (guix packages)
             ;; Власна ліцензія ВОЛЬНІСТЬ як обʼєкт Guix: #367, варіант (a).
             ;; Без цього модуля пакет знову оголосив би gpl3+, яким не є.
             (wsm licenses)
             (srfi srfi-1))
(use-service-modules base desktop sddm networking xorg)

;; Локальні інструменти з цього ж репозиторію. Відносний local-file Guix
;; розв'язує від каталогу цього файлу, тобто ".." — корінь репозиторію.
(define wsm-live-tools
  (package
    (name "wsm-live-tools")
    (version "0.2.0")
    (source (local-file ".." "wsm-desktop-source" #:recursive? #t))
    (build-system trivial-build-system)
    (arguments
     (list
      #:modules '((guix build utils))
      #:builder
      #~(begin
          (use-modules (guix build utils))
          (let* ((root #$output)
                 (share (string-append root "/share/wsm"))
                 (bin (string-append root "/bin"))
                 (apps (string-append root "/share/applications"))
                 (python #$(file-append python-3 "/bin/python3"))
                 (pythonpath
                  (string-append
                   "export PYTHONPATH=\"" share
                   "${PYTHONPATH:+:$PYTHONPATH}\"\n"
                   "for d in /run/current-system/profile/lib/python*/site-packages; do\n"
                   "  [ -d \"$d\" ] || continue\n"
                   "  export PYTHONPATH=\"$d:$PYTHONPATH\"\n"
                   "done\n")))
            (mkdir-p share)
            (for-each
             (lambda (dir)
               (copy-recursively (string-append #$source "/" dir)
                                 (string-append share "/" dir)))
             '("wsm_install" "wsm_hwcheck" "schemas"))
            (mkdir-p bin)

            (for-each
             (lambda (spec)
               (let ((path (string-append bin "/" (car spec))))
                 (call-with-output-file path
                   (lambda (port)
                     (display
                      (string-append
                       "#!/bin/sh\n" pythonpath
                       "exec \"" python "\" -m " (cdr spec) " \"$@\"\n")
                      port)))
                 (chmod path #o755)))
             '(("wsm-hwcheck" . "wsm_hwcheck")
               ("wsm-install" . "wsm_install")))

            ;; Збирає докази, потім показує діагностичний план. Диск не змінюється.
            (call-with-output-file (string-append bin "/wsm-install-live")
              (lambda (port)
                (display
                 (string-append
                  "#!/bin/sh\n"
                  "set -eu\n"
                  "report=/tmp/wsm-hwcheck.json\n"
                  "plan=/tmp/wsm-plan.json\n"
                  "\"" root "/bin/wsm-hwcheck\" --output \"$report\"\n"
                  "status=0\n"
                  "\"" root "/bin/wsm-install\" --preflight --report \"$report\" \\\n"
                  "  --backend guix --dry-run --plan-output \"$plan\" || status=$?\n"
                  "printf 'WSM plan: %s (read-only; no disk was changed)\\n' \"$plan\"\n"
                  "exit \"$status\"\n")
                 port)))
            (chmod (string-append bin "/wsm-install-live") #o755)

            (mkdir-p apps)
            (install-file
             (string-append #$source "/share/applications/wsm-install.desktop")
             apps)))))
    (propagated-inputs (list python-jsonschema))
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (synopsis "WSM live preflight tools and Plasma launcher")
    (description "Read-only hardware report, diagnostic-only Guix plan and desktop launcher.")
    (license license-ref-volnist)))

;; Приймання образу — це маркер у послідовній консолі, а не «збірка повернула
;; нуль». Перевірено на опублікованому ISO: у ньому маркера не було, бо цей
;; профіль його не містив, і жодна перевірка не могла пройти.
;;
;; Служба не валить завантаження: якщо консолі немає, маркер просто відсутній.
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
  (host-name "wsm-kde")
  (timezone "Europe/Kyiv")
  (locale "en_US.utf8")
  (label "WSM KDE Live")
  (bootloader (bootloader-configuration
                (bootloader grub-bootloader)
                (targets '("/dev/sdX"))))
  (kernel-arguments (list "console=ttyS0,115200"))
  (file-systems (cons (file-system
                        (device (file-system-label "my-root"))
                        (mount-point "/")
                        (type "ext4"))
                      %base-file-systems))
  (users (cons (user-account
                 (name "wsm")
                 (comment "WSM live user")
                 (group "users")
                 ;; Консольний вхід: логін `wsm`, пароль `wsm` (SHA-512 crypt).
                 (password "$6$saltWSM$cnmIeJgvQ38p5Wy5YgmTnHnFhAtoHwikjDotqpSoIRHdmGjWQWyLKU4L67GZBKvv0YNgBMUqCWmHQC4gFMnoY0")
                 ;; wheel потрібен, щоб sudo працював у live-сесії.
                 (supplementary-groups '("audio" "video" "netdev" "wheel")))
               %base-user-accounts))
  (packages (cons* wsm-live-tools screen
                   (remove (lambda (p)
                             (string=? (package-name p) "man-db"))
                           %base-packages)))
  (services
   (append
    (list wsm-live-ready-marker
          (service network-manager-service-type)
          (service wpa-supplicant-service-type)
          (service elogind-service-type)
          (service plasma-desktop-service-type)
          (service sddm-service-type
                   (sddm-configuration
                     (theme "breeze")
                     (auto-login-user "wsm")
                     (auto-login-session "plasma"))))
    (modify-services %base-services
      ;; Guix allows empty passwords by default for initial system setup.
      ;; A live image must reject empty console logins, including ttyS0.
      (login-service-type config =>
        (login-configuration
         (inherit config)
         (allow-empty-passwords? #f)))))))
