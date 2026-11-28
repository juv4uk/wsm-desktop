;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Native Free Pascal WSM tools. The compiler is a build-time input only.
;; Each executable is packaged independently; neither package propagates FPC,
;; Python, or a schema-validation runtime to its consumers.

(define-module (wsm packages fpc-tools)
  #:use-module (guix build-system gnu)
  #:use-module (guix gexp)
  #:use-module (guix packages)
  #:use-module (gnu packages pascal)
  #:use-module (wsm licenses)
  #:use-module (srfi srfi-13)
  #:export (wsm-hwcheck-fpc wsm-classify-fpc))

(define (wsm-fpc-source)
  (local-file "../.." "wsm-fpc-source"
              #:recursive? #t
              #:select? (lambda (path _stat)
                          (or (string=? path "LICENSE")
                              (string=? path "tools")
                              (string=? path "tools/pascal")
                              (string-prefix? "tools/pascal/" path)))))

(define (make-wsm-fpc-tool package-name package-version build-target test-target install-target synopsis description)
  (package
    (name package-name)
    (version package-version)
    (source (wsm-fpc-source))
    (build-system gnu-build-system)
    (arguments
     (list
      #:tests? #t
      #:phases
      #~(modify-phases %standard-phases
          (delete 'configure)
          (replace 'build
            (lambda* (#:key #:allow-other-keys)
              (invoke "make" "-C" "tools/pascal" #$build-target)))
          (replace 'check
            (lambda* (#:key #:allow-other-keys)
              (invoke "make" "-C" "tools/pascal" #$test-target)))
          (replace 'install
            (lambda* (#:key outputs #:allow-other-keys)
              (invoke "make" "-C" "tools/pascal" #$install-target
                      (string-append "PREFIX=" (assoc-ref outputs "out")))))))
    (native-inputs (list fpc))
    (synopsis synopsis)
    (description description)
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (supported-systems '("x86_64-linux"))
    (license wsm-license))))

(define-public wsm-hwcheck-fpc
  (make-wsm-fpc-tool
   "wsm-hwcheck-fpc"
   "0.1.0"
   "build-wsm-hwcheck"
   "test-wsm-hwcheck"
   "install-wsm-hwcheck"
   "Read-only native hardware evidence collector for WSM Desktop"
   "Reads PCI, USB, storage, display, CPU, and platform identity evidence from
Linux sysfs and procfs, then emits the WSM hardware evidence schema 1.1 report.
It is unprivileged and read-only: it does not load modules, write to devices,
upload data, or infer functional compatibility from driver binding. Free Pascal
is used only while building the executable."))

(define-public wsm-classify-fpc
  (make-wsm-fpc-tool
   "wsm-classify-fpc"
   "0.2.0"
   "build-wsm-classify"
   "test-wsm-classify"
   "install-wsm-classify"
   "Diagnostic hardware classifier for WSM Desktop"
   "Reads a WSM hardware report and summarizes evidence by subsystem. It never
claims CERTIFIED: functional-test results apply only to their named capability,
and untested driver bindings are not presented as functional validation. Free
Pascal is used only while building the executable."))
