;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Native Free Pascal hardware reader.  FPC is a build-time dependency only;
;; the installed binary does not link to the compiler or Python runtime.
;;
;; Scope is deliberately PCI-only until each additional collector section has
;; parity tests and the same read-only/evidence contract.

(define-module (wsm packages fpc-tools)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix build-system gnu)
  #:use-module (gnu packages pascal)
  #:use-module (wsm licenses)
  #:export (wsm-hwcheck-fpc))

(define-public wsm-hwcheck-fpc
  (package
    (name "wsm-hwcheck-fpc")
    (version "0.2.0")
    (source (local-file "../.." "wsm-desktop-source-fpc"
                        #:recursive? #t
                        #:select? (lambda (path _stat)
                                    (not (any (lambda (skip)
                                                (string-contains path skip))
                                              '("/.git" "/__pycache__" "/build"))))))
    (build-system gnu-build-system)
    (arguments
     (list
      #:tests? #f
      #:make-flags
      #~(list (string-append "FPC=" #$(file-append fpc "/bin/fpc")))
      #:phases
      #~(modify-phases %standard-phases
          (delete 'configure)
          (replace 'build
            (lambda* (#:key make-flags #:allow-other-keys)
              (apply invoke "make" "-C" "tools/pascal" "all" make-flags)))
          (replace 'install
            (lambda* (#:key outputs #:allow-other-keys)
              (let* ((out (assoc-ref outputs "out"))
                     (bin (string-append out "/bin")))
                (install-file "tools/pascal/wsm-hwcheck" bin))))))
    (native-inputs (list fpc))
    (synopsis "Read-only PCI inventory tool for WSM Desktop")
    (description
     "Reads PCI identity and driver binding from sysfs and emits a
versioned hardware evidence report.  The tool is a Free Pascal native
executable.  It performs no writes, module operations, MMIO, network
requests, or block-device access.  FPC is needed only at build time.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license wsm-license)))
