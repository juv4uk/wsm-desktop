;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — пакетне визначення власних інструментів для Guix.
;;
;; Перший H170 Free набір складається з цього WSM-owned пакета та upstream
;; linux-libre і mesa, які workflows резолвлять окремо з channels.lock.scm.
;;
;; СТАТУС: не зібрано й не перевірено (у середовищі написання немає Guix).
;; Evaluation/build на pinned official Guix lock:
;; guix time-machine -C channels.lock.scm -- build -L . \
;;   -e '(@ (wsm packages wsm) wsm-tools)'
;;
;; Пакет ставить модулі wsm_hwcheck і wsm_install у site-packages разом зі
;; схемою звіту. Це необхідно, бо wsm_install/cli.py шукає схему відносно
;; батьківського каталогу модуля: у site-packages це означає schemas/ поруч
;; із пакетами, а не в корені репозиторію.

(define-module (wsm packages wsm)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix download)
  #:use-module (guix git-download)
  #:use-module (guix build-system python)
  #:use-module (gnu packages python)
  #:use-module (gnu packages python-xyz)
  #:use-module (guix licenses)
  ;; version-major+minor lives here; without it the module fails to load.
  #:use-module (guix utils)
  ;; `any` comes from SRFI-1 and `string-contains` from SRFI-13. Both are used
  ;; in the source select? predicate below; without these two imports the module
  ;; does not load at all, and the failure appears only when Guix evaluates it.
  #:use-module (srfi srfi-1)
  #:use-module (srfi srfi-13)
  #:export (wsm-tools))

(define-public wsm-tools
  (package
    (name "wsm-tools")
    (version "0.1.0-rc6")
    ;; Relative paths in local-file are resolved against this file, so "../.."
    ;; is the repository root. select? keeps .git and build output out of the
    ;; store: without it the source would embed the whole git directory, which
    ;; differs between clones and makes the build non-reproducible.
    (source (local-file "../.." "wsm-desktop-source"
                        #:recursive? #t
                        #:select? (lambda (path _stat)
                                    (not (any (lambda (skip)
                                                (string-contains path skip))
                                              '("/.git" "/__pycache__" "/build"))))))
    (build-system python-build-system)
    (arguments
     (list
      ;; Тести репозиторію потребують його структури (tests/, scripts/), тому
      ;; вони виконуються в CI, а не в фазі збірки пакета.
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
                ;; copy-file does not promise to preserve executable bits.
                (for-each (lambda (name)
                            (chmod (string-append bin "/" name) #o555))
                          '("wsm-hwcheck" "wsm-install" "wsm-install-live"))))))))
    (propagated-inputs (list python python-jsonschema))
    (synopsis "Read-only hardware evidence tools for WSM Desktop")
    (description
     "Collects a read-only hardware report from sysfs and procfs, validates it
against a versioned schema, and drafts a diagnostic-only installation plan for
the GNU Guix backend.  Nothing in this package writes to a block device, invokes
a system backend, or requires root.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license (license "ВОЛЬНІСТЬ"
                      "file://LICENSE"
                      "LicenseRef-Volnist; see docs/LICENSING.md. source license only; no OSI/FSDG claim."))))
