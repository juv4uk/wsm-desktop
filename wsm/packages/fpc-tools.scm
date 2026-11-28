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
  ;; The installer front end declares the project licence as a record rather
  ;; than approximating it with gpl3+; see wsm/licenses.scm.
  #:use-module (wsm licenses)
  ;; `any' comes from SRFI-1 and `string-contains' from SRFI-13; the source
  ;; select? predicate uses both, and without the imports the module fails to
  ;; load only when Guix evaluates it.
  #:use-module (srfi srfi-1)
  #:use-module (srfi srfi-13)
  #:export (wsm-hwcheck-fpc wsm-classify-fpc wsm-partition-fpc wsm-install-fpc))

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
                (install-file "tools/pascal/wsm-classify" bin)
                (install-file "tools/pascal/wsm-partition" bin)))))))
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

(define-public wsm-partition-fpc
  (package
    (inherit wsm-hwcheck-fpc)
    (name "wsm-partition-fpc")
    (synopsis "Disk layout planner for WSM Desktop, built with FPC")
    (description
     "Builds a partition layout or refuses with a reason.  It plans and stops:
it never runs sgdisk, never opens a block device and never writes.  The sgdisk
invocations are emitted as data for a caller that holds the consent chain.")))

(define-public wsm-install-fpc
  (package
    (name "wsm-install-fpc")
    (version "0.1.0")
    (source (local-file "../.." "wsm-desktop-source-install-fpc"
                        #:recursive? #t
                        #:select? (lambda (path _stat)
                                    (not (any (lambda (skip)
                                                (string-contains path skip))
                                              '("/.git" "/__pycache__" "/build"))))))
    (build-system gnu-build-system)
    (arguments
     (list
      ;; The repository's tests need the repository (tests/, scripts/); they run
      ;; in CI, not in the package build.
      #:tests? #f
      #:make-flags
      #~(list (string-append "FPC=" #$(file-append fpc "/bin/fpc")))
      #:phases
      #~(modify-phases %standard-phases
          (delete 'configure)
          (replace 'build
            (lambda* (#:key make-flags #:allow-other-keys)
              ;; Only this target: the neighbouring hwcheck/classify programs
              ;; have their own package and must not be built twice.
              (apply invoke "make" "-f" "tools/pascal/Makefile"
                     "wsm-install-fpc" make-flags)))
          (replace 'install
            (lambda* (#:key outputs #:allow-other-keys)
              (let* ((out (assoc-ref outputs "out"))
                     (bin (string-append out "/bin")))
                (install-file "tools/pascal/wsm-install-fpc" bin)
                ;; install-file does not promise the executable bit.
                (chmod (string-append bin "/wsm-install-fpc") #o555)))))))
    ;; gnu-build-system already provides make and the rest of the standard
    ;; inputs; fpc is the only addition.
    (native-inputs (list fpc))
    (synopsis "Read-only WSM installer front end, compiled with FPC")
    (description
     "Validates a WSM hardware report and reports whether the installer may
proceed, with the exit codes of the Python front end (0 accepted, 2 refused,
3 blocked on unresolved critical evidence).  The binary parses its own JSON,
selects the report schema version the document declares, and implements the
structural preflight rules that do not need a JSON Schema validator.  It does
not build the draft plan document, and every rule it does not implement is
listed in its source.  It never opens a block device, never spawns a process and
never requires root, so no interpreter, no site-packages and no schema library
enter the runtime closure.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license wsm-license)))
