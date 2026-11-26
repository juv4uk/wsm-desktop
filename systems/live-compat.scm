;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — окремий opt-in Compatibility live-профіль з NVIDIA 580.x.
;;
;; Ціль цього кандидата: NVIDIA GeForce GTX 1050 Ti, PCI ID 10de:1c82
;; (Pascal, GP107). Профіль використовує Nonguix з окремого lock
;; `channels/compatibility.lock.scm`; він не належить до Free profile
;; і не вмикається за замовчуванням.
;;
;; NVIDIA 580.x обрано для цього точного PCI ID на підставі upstream evidence:
;; Linux 580.196.11 перелічує GTX 1050 Ti, а в перевіреному списку Linux
;; 595.45.04 ID 1C82 відсутній. Це обґрунтовує pin для цього target, але
;; не є загальним твердженням про всі Pascal GPU і не доводить, що pinned
;; Nonguix package збігається з 580.196.11.
;;
;; Стан саме цього профілю на 26.11.2026:
;; - pinned Guix/Nonguix package graph та ISO build: локально зібрано в
;;   ізольованому store; точні commit-и й результати наведено в ISO-RELEASE.md.
;; - в ISO перевірено наявність kernel NVIDIA 580.178.04 modules і GP107
;;   firmware; це перевірка складу образу, не доказ завантаження драйвера.
;; - QEMU TCG BIOS boot: гість досяг login prompt; ранній Guile init segfault
;;   лишається зафіксованим діагностичним сигналом. TCG не емулює GTX 1050 Ti.
;; - QEMU UEFI acceptance: окремого доказу наразі немає.
;; - Compatibility .part001–.part006: ще не завантажено до GitHub Release.
;; - NVIDIA binary redistribution: NOT CLEARED. Pinned Nonguix package inherits
;;   patch-elf/patchelf over installed ELF files; compare the exact driver EULA
;;   and obtain licensing review/permission before publishing binary assets.
;; - Physical H170 / GTX 1050 Ti binding, DRM, Vulkan/OpenGL та rendering:
;;   NOT RUN; потрібен окремий boot на цільовій машині.
;; Тести нижче перевіряють лише source-level graph overrides; вони не
;; замінюють повторне Guix evaluation, image rebuild, UEFI або physical acceptance.
;;
;; Жодних тверджень про підтримку GTX 1050 Ti на реальному обладнанні цей
;; файл не робить.
;;
(use-modules (gnu)
             (gnu services shepherd)
             ((gnu packages linux) #:prefix gnu-linux:)
             (gnu packages python)
             (gnu packages python-xyz)
             (gnu packages screen)
             (gnu packages xorg)
             (guix build-system trivial)
             (guix gexp)
             ((guix licenses) #:prefix license:)
             (guix packages)
             (guix utils)
             (srfi srfi-1)
             (nongnu packages linux)
             (nongnu packages nvidia)
             (nongnu services nvidia))
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
    (license license:gpl3+)))

;; Приймання однакове для всіх образів: маркер у послідовній консолі.
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

;; Guix snapshot пакує Mesa 26.2.6 у $out/lib64, але перевірка RUNPATH
;; очікує $out/lib. У Nonguix-драйвері це ламає mesa-for-nvda, тому явно
;; будуємо варіант Mesa з -Dlibdir=lib і підміняємо його у всіх пакетах,
;; які тягнуть за собою Nonguix-драйвер.
;; libglvnd-for-nvda теж meson-пакет: без фіксації libdir він кладе
;; libGL.so.1 у $out/lib64, а patch-elf драйвера шукає $out/lib/libGL.so.1.
(define libglvnd-for-nvda-fixed
  (hidden-package
   (package/inherit libglvnd-for-nvda
     (arguments
      (substitute-keyword-arguments (package-arguments libglvnd-for-nvda)
        ((#:configure-flags flags #~'())
         #~(cons* "-Dlibdir=lib" #$flags)))))))

(define mesa-for-nvda-fixed
  (hidden-package
   (package/inherit mesa-for-nvda
     (arguments
      (substitute-keyword-arguments (package-arguments mesa-for-nvda)
        ((#:configure-flags flags #~'())
         #~(cons* "-Dlibdir=lib" #$flags))))
     ;; mesa-for-nvda propagates libglvnd-for-nvda. Replace that propagated
     ;; input too, so runtime closure and NVIDIA patch inputs use one libdir.
     (propagated-inputs
      (modify-inputs (package-propagated-inputs mesa-for-nvda)
        (replace "libglvnd" libglvnd-for-nvda-fixed))))))

;; Meson у цьому snapshot-і типово встановлює бібліотеки в $out/lib64,
;; а патч-фази Nonguix шукають $out/lib. Фіксуємо libdir для всіх meson-пакетів
;; у ланцюгу NVIDIA, а не тільки для самої Mesa.
(define (with-fixed-mesa p)
  (package/inherit p
    (arguments
     (substitute-keyword-arguments (package-arguments p)
       ((#:configure-flags flags #~'())
        #~(cons* "-Dlibdir=lib" #$flags))))
    (inputs
     (modify-inputs (package-inputs p)
       (replace "mesa" mesa-for-nvda-fixed)))))

;; У pinned Nonguix 6b8897cd драйвер 580 успадковує egl-wayland
;; через nvidia-driver-390; egl-wayland2 належить іншим driver variants.
(define egl-gbm-fixed (with-fixed-mesa egl-gbm))
(define egl-x11-fixed (with-fixed-mesa egl-x11))
(define egl-wayland-fixed (with-fixed-mesa egl-wayland))

(define nvidia-driver-580-fixed
  (package/inherit nvidia-driver-580
    (inputs
     (modify-inputs (package-inputs nvidia-driver-580)
       ;; patch-elf шукає lib/libGL.so.1 у всіх входах; виправлений
       ;; libglvnd дає цей шлях, на відміну від звичайного lib64.
       (prepend libglvnd-for-nvda-fixed)
       (replace "mesa" mesa-for-nvda-fixed)
       (replace "egl-gbm" egl-gbm-fixed)
       (replace "egl-x11" egl-x11-fixed)
       (replace "egl-wayland" egl-wayland-fixed)))))

(define nv-codec-headers-fixed
  (package/inherit nv-codec-headers
    (inputs
     (modify-inputs (package-inputs nv-codec-headers)
       (replace "nvidia-driver" nvidia-driver-580-fixed)))))

(define nvidia-vaapi-driver-fixed
  (package/inherit nvidia-vaapi-driver
    (inputs
     (modify-inputs (package-inputs nvidia-vaapi-driver)
       (replace "nv-codec-headers" nv-codec-headers-fixed)))))

(define nvda-580-fixed
  (package/inherit nvda-580
    (inputs
     (modify-inputs (package-inputs nvda-580)
       (replace "mesa" mesa-for-nvda-fixed)
       (replace "nvidia-driver" nvidia-driver-580-fixed)
       (replace "nvidia-vaapi-driver" nvidia-vaapi-driver-fixed)))
    (propagated-inputs
     (modify-inputs (package-propagated-inputs nvda-580)
       (replace "nvidia-driver" nvidia-driver-580-fixed)))
    (properties `((driver . ,nvidia-driver-580-fixed)))))

;; Ядро під конкретне залізо: починаємо з повного Nonguix linux 7.3.5, але
;; `make localmodconfig LSMOD=...` вимикає всі in-tree модулі, яких немає у
;; whitelist. Це прибирає nouveau/gma500/i915/SCSI-драйвери, які раніше
;; з'їдали понад дві години компіляції, і лишає лише AHCI/NVMe/USB, Killer
;; E2200 (alx), Realtek HDA, NVIDIA DRM-базу та virtio для QEMU TCG.
;; Архітектура залишається x86-64 generic: ми не блокуємо завантаження на
;; інших CPU, а невідоме залізо чесно потрапляє у verdict Unknown.
(define wsm-linux-gp107
  (gnu-linux:customize-linux
   #:name "linux-wsm-gp107"
   #:linux linux
   #:modconfig (local-file "wsm-gp107.modconfig")
   #:configs '()))

(operating-system
  ;; Proprietary NVIDIA modules require the non-libre Linux kernel.
  (kernel wsm-linux-gp107)
  ;; Guix base-initrd hard-codes a generic module list (hid-apple, isci, ...).
  ;; localmodconfig intentionally drops those, so name only modules that this
  ;; hardware-targeted kernel actually ships. NVMe and ext4 are built in.
  (initrd-modules
   (list "ahci" "usb-storage" "uas" "usbhid" "hid-generic"
         "virtio_pci" "virtio_balloon" "virtio_blk" "virtio_net"
         "virtio_console" "virtio_scsi" "isofs" "squashfs"
         "overlay" "nls_utf8" "alx"))
  (host-name "wsm-kde")
  (timezone "Europe/Kyiv")
  (locale "en_US.utf8")
  (label "WSM KDE Live")
  (bootloader (bootloader-configuration
                (bootloader grub-bootloader)
                (targets '("/dev/sdX"))))
  (kernel-arguments (list "console=ttyS0,115200"
                          "modprobe.blacklist=nouveau"
                          "nvidia-drm.modeset=1"))
  (file-systems (cons (file-system
                        (device (file-system-label "my-root"))
                        (mount-point "/")
                        (type "ext4"))
                      %base-file-systems))
  (users (cons (user-account
                 (name "wsm")
                 (comment "WSM live user")
                 (group "users")
                 (password #f)
                 (supplementary-groups '("audio" "video" "netdev")))
               %base-user-accounts))
  ;; man-db викликає profile-hook manual-database, який на 850 записах іде
  ;; понад годину в ізольованому store. Для live ISO man-база не потрібна.
  (packages (cons* wsm-live-tools screen linux-firmware
                   (remove (lambda (p)
                             (string=? (package-name p) "man-db"))
                           %base-packages)))
  (services
   (append
    (list wsm-live-ready-marker
          (service nvidia-service-type
                   (nvidia-configuration
                    (driver nvda-580-fixed)
                    (module nvidia-module-580)
                    (firmware nvidia-firmware)))
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
