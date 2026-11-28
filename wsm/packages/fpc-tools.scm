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
  #:use-module (wsm licenses)
  ;; `any' comes from SRFI-1 and `string-contains' from SRFI-13; the source
  ;; select? predicate uses both, and without the imports the module fails to
  ;; load only when Guix evaluates it.
  #:use-module (srfi srfi-1)
  #:use-module (srfi srfi-13)
  #:export (wsm-hwcheck-fpc wsm-classify-fpc wsm-partition-fpc wsm-profile-fpc wsm-preflight-fpc wsm-install-fpc))

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
                (install-file "tools/pascal/wsm-partition" bin)
                (install-file "tools/pascal/wsm-profile" bin)
                (install-file "tools/pascal/wsm-preflight" bin)
                (install-file "tools/pascal/wsm-install" bin)))))))
    (synopsis "Read-only PCI hardware reader for WSM Desktop, built with FPC")
    (description
     "A native binary that reads PCI identity and driver binding from sysfs and
writes a JSON report. It is the Free Pascal counterpart of the Python
collector: no interpreter or Python library enters the runtime closure.  It
reads only; it never opens a block device and needs no privileges.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license wsm-license)))

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

(define-public wsm-profile-fpc
  (package
    (inherit wsm-hwcheck-fpc)
    (name "wsm-profile-fpc")
    (synopsis "Evidence bundle reader for WSM Desktop, built with FPC")
    (description
     "Checks an evidence bundle before an installation profile is accepted:
schema version, path safety, at least one passing function, duplicate paths and
artifact presence.  Digest verification is deliberately delegated and the
output says so, so no caller mistakes this for a full check.")))

(define-public wsm-preflight-fpc
  (package
    (inherit wsm-hwcheck-fpc)
    (name "wsm-preflight-fpc")
    (synopsis "Pre-install environment checks for WSM Desktop, built with FPC")
    (description
     "Reports whether this machine can install WSM before anything is touched:
required programs, guix, root, an unused mount point, the system declaration and
the instruction set.  The verdict keeps the rule that makes it honest:
incomplete is not a pass, and the exit code differs between fail and
incomplete.")))

(define-public wsm-install-fpc
  (package
    (inherit wsm-hwcheck-fpc)
    (name "wsm-install-fpc")
    (synopsis "Installer frontend for WSM Desktop, built with FPC")
    (description
     "Runs the five readers in order and prints a plan.  It executes only its
sibling binaries, never a shell, and never sgdisk: the layout is a proposal for
review, and the output says applied:false.")))
