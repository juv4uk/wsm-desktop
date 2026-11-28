;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass jobs for the upstream-only H170 Free package manifest.
;; The package roots are defined by drivers/profiles/h170-free-packages.scm and
;; resolved from the exact official Guix channel revision in the job spec.
;;
;; This job resolves Guix derivations. It does not publish substitutes or
;; export NARs. Register it only after owner-controlled WSM channel Phase B
;; authentication has passed through the ordinary Guix trust path.

(define-module (ci cuirass h170-free-packages)
  #:use-module ((gnu ci) #:select (arguments->systems derivation->job))
  #:use-module (guix packages)
  #:use-module (guix profiles)
  #:use-module (ice-9 ftw)
  #:use-module (srfi srfi-1)
  #:export (cuirass-jobs))

(define %h170-free-system "x86_64-linux")

(define (h170-free-package-roots)
  "Load the fixed H170 Free package manifest from the WSM channel checkout."
  (let ((manifest-file (search-path %load-path "drivers/profiles/h170-free-packages.scm")))
    (unless manifest-file
      (error "Cuirass cannot find drivers/profiles/h170-free-packages.scm"))
    (let ((manifest (primitive-load manifest-file)))
      (unless (manifest? manifest)
        (error "H170 Free package source did not evaluate to a Guix manifest"))
      (map manifest-entry-item (manifest-entries manifest)))))

(define (h170-free-package-job store package system)
  "Return one non-grafted package derivation job for PACKAGE on SYSTEM."
  (let* ((name (package-name package))
         (version (package-version package))
         (job-name (string-append "h170-free-" name "-" version "." system))
         (drv (package-derivation store package system #:graft? #f)))
    (derivation->job
     job-name drv
     #:properties `((#:job-type . package)
                    (#:package-name . ,name)
                    (#:package-version . ,version)))))

(define (cuirass-jobs store arguments)
  "Create one Cuirass derivation job for each fixed H170 Free package root."
  (let ((systems
         (filter (lambda (system)
                   (string=? system %h170-free-system))
                 (arguments->systems arguments)))
        (packages (h170-free-package-roots)))
    (unless (pair? systems)
      (error "H170 Free package jobs require x86_64-linux" %h170-free-system))
    (append-map
     (lambda (system)
       (map (lambda (package)
              (h170-free-package-job store package system))
            packages))
     systems)))
