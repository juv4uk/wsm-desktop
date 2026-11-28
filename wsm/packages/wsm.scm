;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — власний пакет апаратної інвентаризації та планування інсталяції.
;;
;; Binary distribution is authorized by ADR 0010. The effective source license
;; remains LicenseRef-Volnist; this package is not represented as GPL, OSI, or
;; GNU FSDG approved. The actual text is shipped as LICENSE (file://LICENSE).

(define-module (wsm packages wsm)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix download)
  #:use-module (guix git-download)
  #:use-module (guix build-system python)
  #:use-module (gnu packages python)
  #:use-module (gnu packages python-xyz)
  #:use-module (guix licenses)
  #:use-module (guix utils)
  #:use-module (srfi srfi-1)
  #:use-module (srfi srfi-13)
  #:export (wsm-tools))

(define-public wsm-tools
  (package
    (name "wsm-tools")
    (version "0.1.0-rc6")
    (source (local-file "../.." "wsm-desktop-source"
                        #:recursive? #t
                        #:select? (lambda (path _stat)
                                    (not (any (lambda (skip)
                                                (string-contains path skip))
                                              '("/.git" "/__pycache__" "/build"))))))
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
                     (bin (string-append out "/bin")))
                (copy-recursively "wsm_hwcheck"
                                  (string-append site "/wsm_hwcheck"))
                (copy-recursively "wsm_install"
                                  (string-append site "/wsm_install"))
                (copy-recursively "schemas"
                                  (string-append site "/schemas"))
                (mkdir-p bin)
                (copy-file "scripts/wsm-hwcheck.sh"
                           (string-append bin "/wsm-hwcheck"))
                (copy-file "scripts/wsm-install.sh"
                           (string-append bin "/wsm-install"))
                (copy-file "scripts/wsm-install-live.sh"
                           (string-append bin "/wsm-install-live"))
                (for-each (lambda (name)
                            (chmod (string-append bin "/" name) #o555))
                          '("wsm-hwcheck" "wsm-install" "wsm-install-live"))))))))
    (propagated-inputs (list python python-jsonschema))
    (synopsis "Read-only hardware evidence tools for WSM Desktop")
    (description
     "Collects read-only hardware evidence from sysfs and procfs, validates it
against a versioned schema, and drafts a diagnostic-only installation plan
for the GNU Guix backend. It does not write to a block device or require root.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license (license "ВОЛЬНІСТЬ"
                      "file://LICENSE"
                      "LicenseRef-Volnist; source license only; no OSI/FSDG claim."))))
