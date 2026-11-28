;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — пакетне визначення власних інструментів для Guix.
;;
;; СТАТУС: рецепт успішно оцінено й зібрано системним GNU Guix 1.5.0
;; 2026-11-28 (EET), з обмеженням -M 2 -c 2:
;;   guix build -L <checkout> -e '(@ (wsm packages wsm) wsm-tools)'
;; Канал lookup/authentication окремо залежить від Phase B trust bootstrap.
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
  #:use-module (gnu packages python-build)
  #:use-module (gnu packages python-xyz)
  #:use-module (wsm licenses)
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
    ;; Closure budget: the first published pack was 399 MB of store, of which
    ;; ~226 MB was three separate Python builds. python-minimal is the first
    ;; cut; the next build measures whether it worked.
    ;;
    ;; python-minimal, not python: the full interpreter drags its own
    ;; test suite and development headers into every consumer's closure.
    ;; The published pack carried three separate Python builds (~226 MB of
    ;; 399 MB); this is the single biggest cut available without touching
    ;; the code.
    (propagated-inputs (list python-minimal python-jsonschema))
    (synopsis "Read-only hardware evidence tools for WSM Desktop")
    (description
     "Collects a read-only hardware report from sysfs and procfs, validates it
against a versioned schema, and drafts a diagnostic-only installation plan for
the GNU Guix backend.  Nothing in this package writes to a block device, invokes
a system backend, or requires root.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license wsm-license)))
