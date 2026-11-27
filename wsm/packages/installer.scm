;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Optional KDE live-session preview frontend.
;; This package is intentionally not included in any live profile.
;; Public redistribution remains pending the WSM license decision in #367.
(define-module (wsm packages installer)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix build-system python)
  #:use-module (guix utils)
  #:use-module (srfi srfi-13)
  #:use-module (gnu packages python)
  #:use-module (gnu packages qt)
  #:use-module (gnu packages kde-frameworks)
  #:use-module (wsm packages wsm)
  #:export (wsm-installer))

(define-public wsm-installer
  (package
    (name "wsm-installer")
    (version "0.1.0")
    (source (local-file "../.." "wsm-desktop-source"
                        #:recursive? #t
                        #:select? (lambda (path _stat)
                                    (not (or (string-contains path "/.git")
                                             (string-contains path "/__pycache__")
                                             (string-contains path "/build"))))))
    (build-system python-build-system)
    (arguments
     (list
      #:tests? #f
      #:phases
      #~(modify-phases %standard-phases
          (delete 'build)
          (replace 'install
            (lambda* (#:key outputs #:allow-other-keys)
              (let* ((out (assoc-ref outputs "out"))
                     (site (string-append out "/lib/python"
                                          #$(version-major+minor
                                             (package-version python))
                                          "/site-packages"))
                     (bin (string-append out "/bin"))
                     (applications (string-append out "/share/applications"))
                     (icons (string-append out
                                           "/share/icons/hicolor/scalable/apps")))
                (copy-recursively "wsm_installer"
                                  (string-append site "/wsm_installer"))
                (mkdir-p bin)
                (copy-file "scripts/wsm-installer"
                           (string-append bin "/wsm-installer"))
                (chmod (string-append bin "/wsm-installer") #o555)
                (mkdir-p applications)
                (copy-file "installer/gui/assets/wsm-installer.desktop"
                           (string-append applications "/wsm-installer.desktop"))
                (mkdir-p icons)
                (copy-file "installer/gui/assets/wsm-installer.svg"
                           (string-append icons "/wsm-installer.svg"))))))))
    (propagated-inputs
     (list python python-pyside-6 kirigami wsm-tools))
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (synopsis "WSM read-only KDE hardware preflight preview")
    (description
     "A PySide6 and KDE Kirigami frontend that reuses WSM hardware-report
validation and diagnostic-only planning. It reads sysfs and procfs, displays
evidence and a read-only disk inventory, and never performs deployment or
block-device mutations. This optional package is not part of the default live
profiles.")
    ;; Do not invent a Guix license value: package redistribution remains
    ;; unapproved until issue #367 resolves the effective WSM license.
    (license #f)))

;; `guix build -f` evaluates the final expression as its package target.
wsm-installer

wsm-installer
