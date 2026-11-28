;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; The FPC edition of the hardware reader.
;;
;; Why a second implementation exists: the Python package propagated the full
;; interpreter, and the published pack carried three separate Python builds
;; (~226 MB of a 399 MB store). A Free Pascal binary is a single native
;; executable: no interpreter, no site-packages, no schema library in the
;; runtime closure.
;;
;; The two implementations are not interchangeable, and the split is deliberate:
;; this one reads PCI identity only. JSON schema validation stays in CI, where
;; Python already exists — putting a validator in the shipped binary would
;; reintroduce exactly the dependency this package removes.

(define-module (wsm packages fpc-tools)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix download)
  #:use-module (guix build-system gnu)
  #:use-module (gnu packages pascal)
  #:use-module (guix licenses)
  ;; `any' comes from SRFI-1 and `string-contains' from SRFI-13; the source
  ;; select? predicate uses both, and without the imports the module fails to
  ;; load only when Guix evaluates it.
  #:use-module (srfi srfi-1)
  #:use-module (srfi srfi-13)
  #:export (wsm-hwcheck-fpc wsm-classify-fpc))

(define-public wsm-hwcheck-fpc
  (package
    (name "wsm-hwcheck-fpc")
    (version "0.1.0")
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
              (apply invoke "make" "-f" "tools/pascal/Makefile" "all" make-flags)))
          (replace 'install
            (lambda* (#:key outputs #:allow-other-keys)
              (let* ((out (assoc-ref outputs "out"))
                     (bin (string-append out "/bin")))
                (install-file "tools/pascal/wsm-hwcheck" bin)
                (install-file "tools/pascal/wsm-classify" bin)))))))
    (synopsis "Read-only PCI hardware reader for WSM Desktop, built with FPC")
    (description
     "A native binary that reads PCI identity and driver binding from sysfs and
writes a JSON report. It is the Free Pascal counterpart of the Python
collector: no interpreter or Python library enters the runtime closure.  It
reads only; it never opens a block device and needs no privileges.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license license:gpl3+)))

(define-public wsm-classify-fpc
  (package
    (inherit wsm-hwcheck-fpc)
    (name "wsm-classify-fpc")
    (synopsis "Diagnostic hardware classification for WSM Desktop, built with FPC")
    (description
     "Reads a hardware report and produces the diagnostic subsystem summary.
It is the Free Pascal counterpart of the Python classifier, and it keeps the
same restraint: a subsystem is KNOWN only when every observed device has a
driver binding or a candidate, a failed function test blocks that, and
CERTIFIED is never emitted because report v1 has no coverage manifest.")))
