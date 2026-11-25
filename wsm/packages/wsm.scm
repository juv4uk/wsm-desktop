;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — пакетне визначення власних інструментів для Guix.
;;
;; СТАТУС: не зібрано й не перевірено (у середовищі написання немає Guix).
;; Перед використанням: guix build -f wsm/packages/wsm.scm
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
  #:export (wsm-tools))

(define-public wsm-tools
  (package
    (name "wsm-tools")
    (version "0.1.0-rc1")
    (source (local-file "../.." "wsm-desktop-source" #:recursive? #t))
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
                                          "/site-packages")))
                (copy-recursively "wsm_hwcheck"
                                  (string-append site "/wsm_hwcheck"))
                (copy-recursively "wsm_install"
                                  (string-append site "/wsm_install"))
                (copy-recursively "schemas"
                                  (string-append site "/schemas"))))))))
    (propagated-inputs (list python-jsonschema))
    (synopsis "Read-only hardware evidence tools for WSM Desktop")
    (description
     "Collects a read-only hardware report from sysfs and procfs, validates it
against a versioned schema, and drafts a diagnostic-only installation plan for
the GNU Guix backend.  Nothing in this package writes to a block device, invokes
a system backend, or requires root.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license gpl3+)))
