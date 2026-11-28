;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Native Free Pascal packages for WSM evidence and installer tooling.
;; Each package installs one executable. The compiler and FCL are build inputs;
;; Python, tests and generated outputs are not part of the installed closure.

(define-module (wsm packages fpc-tools)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix build-system gnu)
  #:use-module (gnu packages pascal)
  #:use-module (wsm licenses)
  #:use-module (srfi srfi-13)
  #:export (wsm-hwcheck-fpc
            wsm-classify-fpc
            wsm-cpu-isa-fpc
            wsm-partition-fpc
            wsm-profile-fpc
            wsm-preflight-fpc))

;; Guix passes absolute entry paths to select? for recursive local-file sources.
;; Keep only the owner licence and the Pascal source/build directory.
(define wsm-fpc-source
  (local-file "../.." "wsm-desktop-source-fpc"
              #:recursive? #t
              #:select? (lambda (path _stat)
                          (or (string-suffix? "/LICENSE" path)
                              (string-suffix? "/tools" path)
                              (string-suffix? "/tools/pascal" path)
                              (string-contains path "/tools/pascal/")))))

(define (wsm-fpc-arguments build-target check-target install-target)
  (list
   #:tests? #t
   #:make-flags
   #~(list (string-append "FPC=" #$(file-append fpc "/bin/fpc")))
   #:phases
   #~(modify-phases %standard-phases
       (delete 'configure)
       (replace 'build
         (lambda* (#:key make-flags #:allow-other-keys)
           (apply invoke "make" "-f" "tools/pascal/Makefile"
                  #$build-target make-flags)))
       (replace 'check
         (lambda* (#:key make-flags #:allow-other-keys)
           (apply invoke "make" "-f" "tools/pascal/Makefile"
                  #$check-target make-flags)))
       (replace 'install
         (lambda* (#:key outputs make-flags #:allow-other-keys)
           (apply invoke "make" "-f" "tools/pascal/Makefile"
                  #$install-target
                  (string-append "PREFIX=" (assoc-ref outputs "out"))
                  make-flags))))))

(define-public wsm-hwcheck-fpc
  (package
    (name "wsm-hwcheck-fpc")
    (version "0.1.0")
    (source wsm-fpc-source)
    (build-system gnu-build-system)
    (arguments (wsm-fpc-arguments "build-hwcheck" "test-hwcheck" "install-hwcheck"))
    (native-inputs (list fpc))
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (synopsis "Native Free Pascal hardware evidence collector")
    (description
     "Collects read-only Linux sysfs and procfs evidence. Unknown facts remain
unknown; the report is local-only and the executable does not upload data,
load modules, update firmware or modify devices.")
    (supported-systems '("x86_64-linux"))
    (license wsm-license)))

(define-public wsm-classify-fpc
  (package
    (name "wsm-classify-fpc")
    (version "0.1.0")
    (source wsm-fpc-source)
    (build-system gnu-build-system)
    (arguments (wsm-fpc-arguments "build-classify" "test-classify" "install-classify"))
    (native-inputs (list fpc))
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (synopsis "Conservative hardware evidence classifier")
    (description
     "Classifies WSM subsystem evidence without turning missing or incomplete
observations into certification. CERTIFIED is not emitted without a complete
coverage manifest.")
    (supported-systems '("x86_64-linux"))
    (license wsm-license)))

(define-public wsm-cpu-isa-fpc
  (package
    (name "wsm-cpu-isa-fpc")
    (version "0.1.2")
    (source wsm-fpc-source)
    (build-system gnu-build-system)
    (arguments (wsm-fpc-arguments "build-isa" "test-isa" "install-isa"))
    (native-inputs (list fpc))
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (synopsis "Conservative x86-64 ISA evidence from all logical processors")
    (description
     "Intersects observed Linux procfs CPU flags across every logical processor
and reports the common x86-64 psABI level. It does not claim silicon inventory
or performance.")
    (supported-systems '("x86_64-linux"))
    (license wsm-license)))

(define-public wsm-partition-fpc
  (package
    (name "wsm-partition-fpc")
    (version "0.1.0")
    (source wsm-fpc-source)
    (build-system gnu-build-system)
    (arguments (wsm-fpc-arguments "build-partition" "test-partition" "install-partition"))
    (native-inputs (list fpc))
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (synopsis "Read-only disk layout planner")
    (description
     "Produces a partition plan or refuses with a reason. It never invokes
sgdisk, opens a block device or writes storage; commands remain data for a
separate caller to review and authorize.")
    (supported-systems '("x86_64-linux"))
    (license wsm-license)))

(define-public wsm-profile-fpc
  (package
    (name "wsm-profile-fpc")
    (version "0.1.0")
    (source wsm-fpc-source)
    (build-system gnu-build-system)
    (arguments (wsm-fpc-arguments "build-profile" "test-profile" "install-profile"))
    (native-inputs (list fpc))
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (synopsis "Read-only evidence bundle validator")
    (description
     "Checks evidence schema version, path safety, duplicate artifact paths,
artifact presence and passing functional evidence. SHA-256 verification is
explicitly delegated and never claimed as complete.")
    (supported-systems '("x86_64-linux"))
    (license wsm-license)))

(define-public wsm-preflight-fpc
  (package
    (name "wsm-preflight-fpc")
    (version "0.1.0")
    (source wsm-fpc-source)
    (build-system gnu-build-system)
    (arguments (wsm-fpc-arguments "build-preflight" "test-preflight" "install-preflight"))
    (native-inputs (list fpc))
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (synopsis "Read-only WSM installation preflight")
    (description
     "Inspects required tools, privileges, an unused mount point, a Guix system
declaration, a supplied hardware report and x86-64 long-mode evidence. It
reports pass, fail or not-run without executing installer operations.")
    (supported-systems '("x86_64-linux"))
    (license wsm-license)))
