;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Native WSM command-line tools built with Free Pascal.
;; Each reader is an independent package with one executable.
;; FPC and GNU make are native build inputs only.

(define-module (wsm packages fpc-tools)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix build-system gnu)
  #:use-module (gnu packages base)
  #:use-module (gnu packages pascal)
  #:use-module (wsm licenses)
  #:use-module (srfi srfi-13)
  #:export (wsm-hwcheck-fpc
            wsm-classify-fpc
            wsm-cpu-isa-fpc
            wsm-partition-fpc
            wsm-profile-fpc
            wsm-preflight-fpc
            wsm-install-fpc))

(define wsm-fpc-source
  (local-file "../.." "wsm-fpc-source"
              #:recursive? #t
              #:select? (lambda (path _stat)
                          (or (string-suffix? "/LICENSE" path)
                              (string-suffix? "/tools" path)
                              (string-suffix? "/tools/pascal" path)
                              (string-contains path "/tools/pascal/")))))

(define (wsm-fpc-arguments build-target executable)
  (list
   #:tests? #f
   #:make-flags
   #~(list (string-append "FPC=" #$(file-append fpc "/bin/fpc"))
           "BUILD_DIR=build")
   #:phases
   #~(modify-phases %standard-phases
       (delete 'configure)
       (replace 'build
         (lambda* (#:key make-flags #:allow-other-keys)
           (apply invoke "make" "-C" "tools/pascal"
                  #$build-target make-flags)))
       (replace 'install
         (lambda* (#:key outputs #:allow-other-keys)
           (let ((bin (string-append (assoc-ref outputs "out") "/bin"))
                 (program (string-append "tools/pascal/build/" #$executable)))
             (mkdir-p bin)
             (install-file program bin)
             (chmod (string-append bin "/" #$executable) #o555)))))))

(define (make-fpc-reader name version target executable synopsis description)
  (package
    (name name)
    (version version)
    (source wsm-fpc-source)
    (build-system gnu-build-system)
    (native-inputs (list fpc gnu-make))
    (arguments (wsm-fpc-arguments target executable))
    (synopsis synopsis)
    (description description)
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (supported-systems '("x86_64-linux"))
    (license wsm-license)))

(define-public wsm-hwcheck-fpc
  (make-fpc-reader
   "wsm-hwcheck-fpc" "0.1.2" "wsm-hwcheck" "wsm-hwcheck"
   "Read-only PCI hardware evidence collector"
   "Reads PCI identity and direct driver binding from Linux sysfs. The native
first slice does not collect CPU, USB, block, DRM, or firmware-log evidence;
these facts remain unknown rather than being inferred. Driver binding is not
functional certification."))

(define-public wsm-classify-fpc
  (make-fpc-reader
   "wsm-classify-fpc" "0.1.2" "wsm-classify" "wsm-classify"
   "Conservative hardware evidence classifier"
   "Classifies subsystem evidence from a WSM Hardware Evidence Report.
Inventory and driver binding do not prove functional operation; CERTIFIED
remains unavailable without complete coverage and functional-test evidence."))

(define-public wsm-cpu-isa-fpc
  (make-fpc-reader
   "wsm-cpu-isa-fpc" "0.1.2" "wsm-cpu-isa" "wsm-cpu-isa"
   "Common x86-64 ISA evidence from all logical processors"
   "Intersects Linux procfs CPU flags across every logical processor and
reports common x86-64 psABI feature levels. Incomplete processor evidence is
refused. This is kernel-exposed capability evidence, not a benchmark."))

(define-public wsm-partition-fpc
  (make-fpc-reader
   "wsm-partition-fpc" "0.1.2" "wsm-partition" "wsm-partition"
   "Read-only whole-disk partition layout planner"
   "Validates a whole-disk path and exact acknowledgement, then emits a plan
as JSON. It never opens a block device, invokes sgdisk, or writes a partition
table."))

(define-public wsm-profile-fpc
  (make-fpc-reader
   "wsm-profile-fpc" "0.1.2" "wsm-profile" "wsm-profile"
   "Semantic reader for WSM hardware evidence bundles"
   "Checks the supported evidence schema, safe relative artifact paths,
duplicate paths, artifact existence, and presence of a passing function.
Digest verification remains explicitly delegated and is not claimed here."))

(define-public wsm-preflight-fpc
  (make-fpc-reader
   "wsm-preflight-fpc" "0.1.0" "wsm-preflight" "wsm-preflight"
   "Read-only WSM installation preflight"
   "Checks installation prerequisites and hardware evidence inputs. A
not-run criterion produces incomplete, never pass. It reads system facts and
does not modify target devices."))

(define-public wsm-install-fpc
  (package
    (name "wsm-install-fpc")
    (version "0.1.0")
    (source wsm-fpc-source)
    (build-system gnu-build-system)
    (native-inputs (list fpc gnu-make))
    (inputs (list wsm-preflight-fpc
                  wsm-hwcheck-fpc
                  wsm-classify-fpc
                  wsm-partition-fpc))
    (arguments
     (list
      #:tests? #f
      #:make-flags
      #~(list (string-append "FPC=" #$(file-append fpc "/bin/fpc"))
              "BUILD_DIR=build")
      #:phases
      #~(modify-phases %standard-phases
          (delete 'configure)
          (replace 'build
            (lambda* (#:key make-flags #:allow-other-keys)
              (apply invoke "make" "-C" "tools/pascal"
                     "wsm-install" make-flags)))
          (replace 'install
            (lambda* (#:key outputs inputs #:allow-other-keys)
              (let ((bin (string-append (assoc-ref outputs "out") "/bin")))
                (mkdir-p bin)
                (install-file "tools/pascal/build/wsm-install" bin)
                (for-each
                 (lambda (entry)
                   (let* ((input (assoc-ref inputs (car entry)))
                          (executable (cdr entry)))
                     (symlink (string-append input "/bin/" executable)
                              (string-append bin "/" executable))))
                 '(("wsm-preflight-fpc" . "wsm-preflight")
                   ("wsm-hwcheck-fpc" . "wsm-hwcheck")
                   ("wsm-classify-fpc" . "wsm-classify")
                   ("wsm-partition-fpc" . "wsm-partition"))))))))
    (synopsis "Native Free Pascal WSM installation orchestrator")
    (description
     "Runs the native installer frontend with the four read-only tools it
actually invokes: preflight, hardware collection, classification, and the
partition planner. It does not enable destructive APPLY or write to disks.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (supported-systems '("x86_64-linux"))
    (license wsm-license)))
