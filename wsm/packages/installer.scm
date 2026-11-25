;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Separate package module for the WSM-owned Qt/QML frontend.
;; Keep this file independent from wsm/packages/wsm.scm so the live-ISO
;; executor can integrate it without colliding with the Python tools package.

(define-module (wsm packages installer)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix build-system cmake)
  #:use-module (gnu packages cmake)
  #:use-module (gnu packages python)
  #:use-module (gnu packages linux)
  #:use-module (gnu packages qt)
  #:use-module (wsm packages wsm)
  #:export (wsm-installer))

;; Custom LicenseRef-Volnist has not been accepted as a Guix license
;; record yet. Do not mislabel it as GPL or assert Free eligibility.
(define-public wsm-installer
  (package
    (name "wsm-installer")
    (version "0.1.0")
    (source (local-file "../../installer/gui"
                         "wsm-installer-source"
                         #:recursive? #t))
    (build-system cmake-build-system)
    (arguments
     (list
      #:configure-flags
      #~(list
         "-DCMAKE_BUILD_TYPE=Release"
         (string-append "-DWSM_PYTHON_EXECUTABLE="
                        #$(file-append python "/bin/python3"))
         (string-append "-DWSM_QML_IMPORT_PATH="
                        #$(file-append qtdeclarative "/lib/qt6/qml"))
         (string-append "-DWSM_GUIX_PYTHONPATH="
                        (or (getenv "GUIX_PYTHONPATH") ""))
         (string-append "-DWSM_LSBLK_EXECUTABLE="
                        #$(file-append util-linux "/bin/lsblk")))))
    (native-inputs (list cmake))
    (inputs (list qtbase qtdeclarative))
    (propagated-inputs (list python wsm-tools util-linux))
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (synopsis "WSM-owned Qt/QML hardware preflight frontend")
    (description
     "A Ukrainian Qt Quick desktop frontend for the read-only WSM hardware
preflight and diagnostic-only installation preview.  It does not partition,
format, mount, or deploy to block devices.")
    (license #f)))
