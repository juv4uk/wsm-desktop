;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Native WSM tools built with Free Pascal. Reader packages contain one
;; executable each. The installer declares the readers as runtime inputs and
;; exposes their binaries beside its own frontend.

(define-module (wsm packages fpc-tools)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix build-system gnu)
  #:use-module (gnu packages pascal)
  #:use-module (wsm licenses)
  #:use-module (srfi srfi-1)
  #:use-module (srfi srfi-13)
  #:export (wsm-hwcheck-fpc
            wsm-classify-fpc
            wsm-partition-fpc
            wsm-profile-fpc
            wsm-preflight-fpc
            wsm-install-fpc))

(define fpc-source
  (local-file "../.." "wsm-desktop-source-fpc"
              #:recursive? #t
              #:select? (lambda (path _stat)
                          (not (any (lambda (skip)
                                      (string-contains path skip))
                                    '("/.git" "/__pycache__" "/build"))))))

(define (fpc-package-arguments make-target executable)
  (list
   #:tests? #f
   #:make-flags
   #~(list (string-append "FPC=" #$(file-append fpc "/bin/fpc")))
   #:phases
   #~(modify-phases %standard-phases
       (delete 'configure)
       (replace 'build
         (lambda* (#:key make-flags #:allow-other-keys)
           (apply invoke "make" "-C" "tools/pascal" #$make-target make-flags)))
       (replace 'install
         (lambda* (#:key outputs #:allow-other-keys)
           (let* ((out (assoc-ref outputs "out"))
                  (bin (string-append out "/bin"))
                  (program (string-append "tools/pascal/build/" #$executable)))
             (install-file program bin)))))))

(define (make-fpc-reader name target executable synopsis description)
  (package
    (name name)
    (version "0.1.1")
    (source fpc-source)
    (build-system gnu-build-system)
    (native-inputs (list fpc))
    (arguments (fpc-package-arguments target executable))
    (synopsis synopsis)
    (description description)
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license wsm-license)))

(define-public wsm-hwcheck-fpc
  (make-fpc-reader
   "wsm-hwcheck-fpc" "wsm-hwcheck" "wsm-hwcheck"
   "Read-only PCI evidence collector for WSM Desktop"
   "Reads PCI identity and direct driver binding from sysfs and emits a
Hardware Evidence Report 1.1.0 JSON document. This collector reports PCI only;
it does not infer CPU, USB, block, DRM, firmware-log or functional-test facts.
The compiler is a build-time input only."))

(define-public wsm-classify-fpc
  (make-fpc-reader
   "wsm-classify-fpc" "wsm-classify" "wsm-classify"
   "Diagnostic subsystem classifier for WSM Desktop"
   "Reads a hardware report and emits a diagnostic subsystem summary. It
never claims CERTIFIED because the report does not carry a complete coverage
manifest. The compiler is a build-time input only."))

(define-public wsm-partition-fpc
  (make-fpc-reader
   "wsm-partition-fpc" "wsm-partition" "wsm-partition"
   "Read-only GPT layout planner for WSM Desktop"
   "Validates a whole-disk target and explicit acknowledgement, then emits a
partition plan as JSON data. It never opens a block device, invokes sgdisk or
writes a partition table. The compiler is a build-time input only."))

(define-public wsm-profile-fpc
  (make-fpc-reader
   "wsm-profile-fpc" "wsm-profile" "wsm-profile"
   "Evidence bundle preflight reader for WSM Desktop"
   "Checks the evidence-bundle version, canonical relative paths, artifact
presence, duplicate paths and at least one passing function. It does not
replace the full JSON Schema or SHA-256 validator; digest verification is
explicitly delegated to the Python reference validator."))

(define-public wsm-preflight-fpc
  (make-fpc-reader
   "wsm-preflight-fpc" "wsm-preflight" "wsm-preflight"
   "Pre-install system readiness checks for WSM Desktop"
   "Checks required tools, Guix, privileges, mount-point availability,
system declaration, hardware-report presence and instruction-set support.
It distinguishes a failure from an incomplete check and performs no writes."))

(define (fpc-installer-arguments)
  (list
   #:tests? #f
   #:make-flags
   #~(list (string-append "FPC=" #$(file-append fpc "/bin/fpc")))
   #:phases
   #~(modify-phases %standard-phases
       (delete 'configure)
       (replace 'build
         (lambda* (#:key make-flags #:allow-other-keys)
           (apply invoke "make" "-C" "tools/pascal" "wsm-install" make-flags)))
       (replace 'install
         (lambda* (#:key outputs inputs #:allow-other-keys)
           (let* ((out (assoc-ref outputs "out"))
                  (bin (string-append out "/bin")))
             (install-file "tools/pascal/build/wsm-install" bin)
             ;; wsm-install resolves its reader executables beside the frontend.
             (for-each
              (lambda (entry)
                (let* ((input (assoc-ref inputs (car entry)))
                       (program (cdr entry)))
                  (symlink (string-append input "/bin/" program)
                           (string-append bin "/" program))))
              '(("wsm-preflight-fpc" . "wsm-preflight")
                ("wsm-hwcheck-fpc" . "wsm-hwcheck")
                ("wsm-classify-fpc" . "wsm-classify")
                ("wsm-partition-fpc" . "wsm-partition")
                ("wsm-profile-fpc" . "wsm-profile")))))))))

(define-public wsm-install-fpc
  (package
    (name "wsm-install-fpc")
    (version "0.1.1")
    (source fpc-source)
    (build-system gnu-build-system)
    (native-inputs (list fpc))
    (inputs (list wsm-preflight-fpc
                  wsm-hwcheck-fpc
                  wsm-classify-fpc
                  wsm-partition-fpc
                  wsm-profile-fpc))
    (arguments (fpc-installer-arguments))
    (synopsis "Installer frontend with separate native readers for WSM Desktop")
    (description
     "Runs the WSM preflight, hardware, classification and partition readers
in order. The five reader packages are explicit runtime inputs and are exposed
beside the frontend through symlinks. The partition planner only emits a plan
and never writes a disk.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license wsm-license)))
