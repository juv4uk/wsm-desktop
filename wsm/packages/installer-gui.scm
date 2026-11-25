;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM-owned Qt/QML frontend. Kept separate from the live image recipe
;; so the ISO owner can integrate it without editing overlapping files.

(define-module (wsm packages installer-gui)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix build-system cmake)
  #:use-module (gnu packages python)
  #:use-module (gnu packages qt)
  #:use-module (wsm packages wsm)
  #:export (wsm-installer-gui))

(define-public wsm-installer-gui
  (package
    (name "wsm-installer-gui")
    (version "0.1.0")
    (source (local-file "../../installer/gui" "wsm-installer-gui-source"
                        #:recursive? #t))
    (build-system cmake-build-system)
    (arguments
     (list
      #:tests? #f
      #:configure-flags
      #~(list
         (string-append
          "-DWSM_PYTHONPATH=" #$wsm-tools
          "/lib/python"
          #$(version-major+minor (package-version python))
          "/site-packages"))))
    (propagated-inputs
     (list python wsm-tools qtbase qtdeclarative))
    (synopsis "WSM Desktop read-only graphical installer frontend")
    (description
     "Provides the WSM-owned Qt 6/QML preflight interface for the live desktop.
It collects read-only hardware evidence, lists block devices without modifying
them, and displays a diagnostic-only Guix plan. It does not partition disks,
format filesystems, install a bootloader, or invoke Guix deployment.")
    ;; The custom LicenseRef-Volnist has not been classified as an approved
    ;; Guix license object. Do not mislabel this source as GPL or as Free.
    (license #f)
    (home-page "https://github.com/juv4uk/wsm-desktop")))
