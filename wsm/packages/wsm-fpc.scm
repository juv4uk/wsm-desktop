;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Native Free Pascal hardware evidence collector. The compiler is a native
;; build input only; the installed executable has no Python/FCL package
;; dependency and does not invoke external tools at runtime.

(define-module (wsm packages wsm-fpc)
  #:use-module (guix build-system gnu)
  #:use-module (guix gexp)
  #:use-module (gnu packages pascal)
  #:use-module (guix packages)
  #:use-module (wsm licenses)
  #:use-module (srfi srfi-13)
  #:export (wsm-hwcheck-fpc))

(define-public wsm-hwcheck-fpc
  (package
    (name "wsm-hwcheck-fpc")
    (version "0.1.0")
    (source
     (local-file "../.." "wsm-hwcheck-fpc-source"
                 #:recursive? #t
                 #:select? (lambda (path _stat)
                             (or (string=? path "LICENSE")
                                 (string=? path "tools")
                                 (string-prefix? "tools/fpc/" path)))))
    (build-system gnu-build-system)
    (arguments
     (list
      #:tests? #t
      #:phases
      #~(modify-phases %standard-phases
          (delete 'configure)
          (replace 'build
            (lambda* (#:key #:allow-other-keys)
              (invoke "make" "-f" "tools/fpc/Makefile" "build")))
          (replace 'check
            (lambda* (#:key #:allow-other-keys)
              (invoke "make" "-f" "tools/fpc/Makefile" "test")))
          (replace 'install
            (lambda* (#:key outputs #:allow-other-keys)
              (invoke "make" "-f" "tools/fpc/Makefile" "install"
                      (string-append "PREFIX=" (assoc-ref outputs "out")))))))
    (native-inputs (list fpc))
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (synopsis "Native Free Pascal Linux hardware evidence collector")
    (description
     "Collects a strict-local, read-only WSM hardware evidence report from
Linux sysfs and procfs. The compiler is used only at build time. The
executable does not upload data, load modules, update firmware, or modify
target devices. Missing facts remain unknown; inventory is not a functional
compatibility test.")
    (supported-systems '("x86_64-linux"))
    (license wsm-license)))
