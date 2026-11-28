;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Native WSM utilities built with Free Pascal. FPC is a build-time dependency;
;; none propagates the compiler or any Python runtime.

(define-module (wsm packages fpc-tools)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix build-system gnu)
  #:use-module (gnu packages pascal)
  #:use-module (wsm licenses)
  #:use-module (srfi srfi-1)
  #:use-module (srfi srfi-13)
  #:export (wsm-hwcheck-fpc wsm-classify-fpc wsm-partition-fpc wsm-profile-fpc))

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

(define-public wsm-hwcheck-fpc
  (package
    (name "wsm-hwcheck-fpc")
    (version "0.1.1")
    (source (local-file "../.." "wsm-desktop-source-fpc"
                        #:recursive? #t
                        #:select? (lambda (path _stat)
                                    (not (any (lambda (skip)
                                                (string-contains path skip))
                                              '("/.git" "/__pycache__" "/build"))))))
    (build-system gnu-build-system)
    (native-inputs (list fpc))
    (arguments (fpc-package-arguments "wsm-hwcheck" "wsm-hwcheck"))
    (synopsis "Read-only PCI hardware evidence collector for WSM Desktop")
    (description
     "A native Free Pascal utility that reads PCI identity and direct driver
binding from sysfs and emits a WSM Hardware Evidence Report v1.1.0 JSON
document. The collector is PCI-only: it does not collect CPU, USB, block,
DRM or firmware-log facts, and it does not prove device functionality.
The FPC compiler is used only at build time.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license wsm-license)))

(define-public wsm-classify-fpc
  (package
    (name "wsm-classify-fpc")
    (version "0.1.1")
    (source (local-file "../.." "wsm-desktop-source-fpc"
                        #:recursive? #t
                        #:select? (lambda (path _stat)
                                    (not (any (lambda (skip)
                                                (string-contains path skip))
                                              '("/.git" "/__pycache__" "/build"))))))
    (build-system gnu-build-system)
    (native-inputs (list fpc))
    (arguments (fpc-package-arguments "wsm-classify" "wsm-classify"))
    (synopsis "Diagnostic subsystem classifier for WSM Desktop")
    (description
     "A native Free Pascal utility that reads a WSM hardware evidence report
and emits the diagnostic subsystem summary. It never claims CERTIFIED because
report v1 has no complete coverage manifest. The FPC compiler is used only at
build time.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license wsm-license)))


(define-public wsm-partition-fpc
  (package
    (name "wsm-partition-fpc")
    (version "0.1.1")
    (source (local-file "../.." "wsm-desktop-source-fpc"
                        #:recursive? #t
                        #:select? (lambda (path _stat)
                                    (not (any (lambda (skip)
                                                (string-contains path skip))
                                              '("/.git" "/__pycache__" "/build"))))))
    (build-system gnu-build-system)
    (native-inputs (list fpc))
    (arguments (fpc-package-arguments "wsm-partition" "wsm-partition"))
    (synopsis "Read-only disk layout planner for WSM Desktop")
    (description
     "A native Free Pascal utility that validates an explicitly acknowledged
whole-disk target and emits a partition layout as JSON. It never invokes
sgdisk, opens a block device, or writes a partition table. The FPC compiler
is used only at build time.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license wsm-license)))


(define-public wsm-profile-fpc
  (package
    (name "wsm-profile-fpc")
    (version "0.1.1")
    (source (local-file "../.." "wsm-desktop-source-fpc"
                        #:recursive? #t
                        #:select? (lambda (path _stat)
                                    (not (any (lambda (skip)
                                                (string-contains path skip))
                                              '("/.git" "/__pycache__" "/build"))))))
    (build-system gnu-build-system)
    (native-inputs (list fpc))
    (arguments (fpc-package-arguments "wsm-profile" "wsm-profile"))
    (synopsis "Evidence bundle reader for WSM Desktop")
    (description
     "Checks a WSM profile evidence bundle before a profile is accepted:
schema version, path safety, at least one passing function, duplicate paths
and artifact presence. Digest verification is explicitly delegated; the
reader does not write or execute anything.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license wsm-license)))
