;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass jobs for H170 Free package roots, all from the pinned official Guix channel.
;; This is a development build coordinator, not a license grant or substitute publisher.
;;
(define-module (ci cuirass h170-free-packages)
  #:use-module ((gnu ci) #:select (arguments->systems derivation->job))
  #:use-module (guix packages)
  #:use-module (guix profiles)
  #:use-module (ice-9 ftw)
  #:use-module (srfi srfi-1)
  #:export (cuirass-jobs))

(define %h170-free-system "x86_64-linux")

(define (h170-free-packages)
  "Load only the package roots declared by the H170 Free manifest."
  (let ((manifest-file (search-path %load-path "manifests/h170-free-upstream.scm")))
    (unless manifest-file
      (error "Cuirass cannot find manifests/h170-free-upstream.scm"))
    (let ((manifest (primitive-load manifest-file)))
      (unless (manifest? manifest)
        (error "H170 Free upstream file did not evaluate to a Guix manifest"))
      (map manifest-entry-item (manifest-entries manifest)))))

(define (h170-free-package->job store package system)
  "Return one non-grafted Cuirass derivation job for PACKAGE on SYSTEM."
  (let* ((name (package-name package))
         (version (package-version package))
         (job-name (string-append "h170-free-" name "-" version "." system))
         (derivation (package-derivation store package system #:graft? #f)))
    (derivation->job
     job-name derivation
     #:properties `((#:job-type . package)
                    (#:package-name . ,name)
                    (#:package-version . ,version)))))

(define (cuirass-jobs store arguments)
  "Build Cuirass package jobs for the H170 Free upstream package roots."
  (let ((systems
         (filter (lambda (system)
                   (string=? system %h170-free-system))
                 (arguments->systems arguments)))
        (packages (h170-free-packages)))
    (unless (pair? systems)
      (error "H170 Free package job requires x86_64-linux" %h170-free-system))
    (append-map
     (lambda (system)
       (map (lambda (package)
              (h170-free-package->job store package system))
            packages))
     systems)))
