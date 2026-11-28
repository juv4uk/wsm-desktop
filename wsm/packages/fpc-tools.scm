;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Native Free Pascal hardware evidence collector and conservative classifier.
;; FPC and its FCL units are build-only inputs; the installed executables do
;; not depend on a Python interpreter or invoke Python at runtime.

(define-module (wsm packages fpc-tools)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix build-system gnu)
  #:use-module (gnu packages pascal)
  #:use-module (wsm licenses)
  #:use-module (srfi srfi-1)
  #:use-module (srfi srfi-13)
  #:export (wsm-hwcheck-fpc wsm-classify-fpc))

(define-public wsm-hwcheck-fpc
  (package
    (name "wsm-hwcheck-fpc")
    (version "0.1.0")
    (source
     (local-file "../.." "wsm-desktop-source-fpc"
                 #:recursive? #t
                 #:select? (lambda (path _stat)
                             (not (any (lambda (skip)
                                         (string-contains path skip))
                                       '("/.git" "/__pycache__" "/build"))))))
    (build-system gnu-build-system)
    (arguments
     (list
      #:tests? #t
      #:make-flags
      #~(list (string-append "FPC=" #$(file-append fpc "/bin/fpc")))
      #:phases
      #~(modify-phases %standard-phases
          (delete 'configure)
          (replace 'build
            (lambda* (#:key make-flags #:allow-other-keys)
              (apply invoke "make" "-f" "tools/pascal/Makefile" "build" make-flags)))
          (replace 'check
            (lambda* (#:key make-flags #:allow-other-keys)
              (apply invoke "make" "-f" "tools/pascal/Makefile" "test" make-flags)))
          (replace 'install
            (lambda* (#:key outputs make-flags #:allow-other-keys)
              (apply invoke "make" "-f" "tools/pascal/Makefile" "install"
                     (string-append "PREFIX=" (assoc-ref outputs "out"))
                     make-flags)))))
    (native-inputs (list fpc))
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (synopsis "Native Free Pascal hardware evidence tools for WSM Desktop")
    (description
     "Builds a read-only hardware evidence collector and a conservative
subsystem classifier using Free Pascal. The collector reads local sysfs and
procfs, preserves unknown facts, and emits the versioned WSM hardware report.
The classifier never promotes inventory to certification. FPC is used only
at build time; neither executable requires Python or performs network,
firmware, module-loading, or target-device write operations.")
    (supported-systems '("x86_64-linux"))
    (license wsm-license)))

(define-public wsm-classify-fpc
  (package
    (inherit wsm-hwcheck-fpc)
    (name "wsm-classify-fpc")
    (synopsis "Conservative native Free Pascal hardware evidence classifier")
    (description
     "Reads a WSM hardware evidence report and emits conservative subsystem
evidence states. A subsystem is KNOWN only when every observed device has a
bound driver or a candidate and no functional test failed. CERTIFIED remains
zero because the current report has no complete coverage manifest.")))
