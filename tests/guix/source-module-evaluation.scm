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
             (srfi srfi-1)
             (gnu ci)
             (gnu services)
             (gnu services cuirass)
             (guix gexp)
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


;; Exercise the real custom-job callback. This lowers the ISO image to a
;; derivation using the exact pinned Guix API, but does not build the ISO.
(with-store store
  (let* ((jobs (cuirass-jobs store '((systems . ("x86_64-linux")))))
         (job (and (pair? jobs) (car jobs)))
         (name (and job (assq-ref job #:job-name)))
         (drv (and job (assq-ref job #:derivation))))
    (unless (and (= (length jobs) 1)
                 (equal? name "wsm-live-minimal-image.x86_64-linux")
                 (string? drv)
                 (> (string-length drv) 0))
      (error "Cuirass custom job did not produce the expected ISO derivation"
             jobs))))

;; Load and instantiate the actual service helper using a harmless empty gexp.
;; This checks the pinned service type/configuration without registering Cuirass.
(primitive-load "ci/cuirass/service.scm")
(define %wsm-cuirass-service-smoke
  (wsm-cuirass-service #~'()))
(unless (service? %wsm-cuirass-service-smoke)
  (error "Cuirass service helper did not return a Guix service"))

(display "WSM-CUIRASS-IMAGE-JOB-EVAL-OK: ISO derivation generated, not built")
(newline)
(display "WSM-CUIRASS-SERVICE-EVAL-OK")
(newline)

(display "WSM-SOURCE-MODULE-EVAL-OK ")
(display (length %wsm-performance-services))
(display " services, channel package: ")
(display (package-name wsm-tools))
(display " ")
(display (package-version wsm-tools))
(newline)
