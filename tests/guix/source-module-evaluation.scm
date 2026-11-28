;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Source-tree Guix API/evaluation compatibility check against the exact
;; official Guix lock. This does not exercise WSM channel lookup/authentication.
;; The latter requires the owner's signed introduction and a dedicated lock.
;;
;; Every module under wsm/ must be loaded here: this file is the only place
;; where source modules are evaluated by Guix for real, so a module missing
;; from this list is a module nobody has checked.
;; scripts/check_scheme_module_coverage.py enforces that rule.
(use-modules (guix packages)
             (guix store)
             (gnu services)
             (ice-9 ftw)
             (srfi srfi-1)
             (ci cuirass images)
             (wsm systems performance)
             (wsm packages wsm))

(unless (and (list? %wsm-performance-services)
             (pair? %wsm-performance-services))
  (error "WSM performance module exported no service definitions"))

;; The channel's own package module: until it is loaded here it was never
;; evaluated, and its header said so ("не зібрано й не перевірено").
(unless (package? wsm-tools)
  (error "WSM package module did not export a package record for wsm-tools"))

(display "WSM-SOURCE-MODULE-EVAL-OK ")
(display (length %wsm-performance-services))
(display " services, channel package: ")
(display (package-name wsm-tools))
(display " ")
(display (package-version wsm-tools))
(newline)

;; Invoke the actual Cuirass custom entry point with the argument shape Cuirass
;; passes (plural 'systems). This lowers the ISO image derivation through Guix's
;; image->job helper and checks the resulting job record without building it.
;; Simulate a worker whose process CWD is outside the checkout: the profile must
;; be found through the absolute channel checkout added to Guile's load path.
(define %original-directory (getcwd))
(define %wsm-channel-root (canonicalize-path "."))
(set! %load-path (cons %wsm-channel-root %load-path))
(chdir "/tmp")
(define cuirass-image-jobs
  (cuirass-jobs (open-connection) '((systems . ("x86_64-linux")))))
(chdir %wsm-channel-root)
(unless (and (list? cuirass-image-jobs)
             (= (length cuirass-image-jobs) 1))
  (error "Cuirass image job did not honor the requested systems list"))
(let ((job (car cuirass-image-jobs)))
  (unless (string=? (assq-ref job #:job-name)
                    "wsm-live-minimal.x86_64-linux")
    (error "Cuirass image job has an unexpected name"))
  (unless (and (string? (assq-ref job #:derivation))
               (string=? (assq-ref job #:system) "x86_64-linux")
               (eq? (assq-ref job #:job-type) 'image))
    (error "Cuirass image job did not return an image derivation record")))

;; Load the actual service fragment against the same pinned Guix API.
(primitive-load "ci/cuirass/service.scm")
(unless (service? wsm-cuirass-service)
  (error "Cuirass service fragment did not define a Guix service"))

(display "WSM-CUIRASS-IMAGE-JOB-EVAL-OK")
(newline)
