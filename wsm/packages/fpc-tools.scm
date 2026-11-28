;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Native Free Pascal hardware evidence collector and conservative classifier.
;; Each Guix package installs only its own executable. FPC is a native/build
;; input; no compiler, Python runtime or propagated dependency enters runtime.

(define-module (wsm packages fpc-tools)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix build-system gnu)
  #:use-module (gnu packages pascal)
  #:use-module (wsm licenses)
  #:use-module (srfi srfi-13)
  #:export (wsm-hwcheck-fpc wsm-classify-fpc wsm-cpu-isa-fpc))

;; Keep the build source narrow and reproducible: LICENSE plus the Pascal
;; programs and Makefile only. Python sources, documentation, test fixtures,
;; generated files and the Git checkout never enter this source object.
(define wsm-fpc-source
  (local-file "../.." "wsm-desktop-source-fpc"
              #:recursive? #t
              #:select? (lambda (path _stat)
                          (or (string=? path "LICENSE")
                              (string=? path "tools")
                              (string=? path "tools/pascal")
                              (string-prefix? "tools/pascal/" path)))))

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
     "Collects a read-only WSM hardware evidence report from Linux sysfs and
procfs. The report preserves unknown facts, uses the WSM schema version 1.1.0,
and declares strict-local privacy. The executable does not upload data, load
modules, update firmware, or modify target devices.")
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
    (synopsis "Conservative Free Pascal hardware evidence classifier")
    (description
     "Reads a WSM hardware evidence report and emits conservative subsystem
evidence states. A subsystem is KNOWN only when each observed device has a
bound driver or a candidate and no functional test failed. CERTIFIED remains
zero because the current report has no complete coverage manifest.")
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
     "Reads the Linux procfs CPU flags exposed for every logical processor and
reports the common x86-64 psABI levels. It refuses incomplete processor-block
evidence, intersects flags instead of trusting CPU 0, and distinguishes
observed kernel flags from silicon inventory or performance claims. The
executable is read-only and has no Python runtime dependency.")
    (supported-systems '("x86_64-linux"))
    (license wsm-license)))
