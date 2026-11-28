;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Evaluate WSM Scheme modules and Cuirass API against the exact Guix lock.
;;
;; This lowers the live ISO expression to a derivation but does not build it,
;; register a jobset, authenticate the remote WSM channel, or start Cuirass.

(use-modules (guix packages)
             (guix store)
             (gnu services)
             (gnu services cuirass)
             ((ci cuirass images) #:select (cuirass-jobs))
             (wsm systems performance)
             (wsm packages wsm))

(unless (and (list? %wsm-performance-services)
             (pair? %wsm-performance-services))
  (error "WSM performance module exported no service definitions"))

(unless (package? wsm-tools)
  (error "WSM package module did not export a package record for wsm-tools"))

;; Exercise the actual custom callback and verify the lowered ISO derivation.
(with-store store
  (let* ((jobs (cuirass-jobs store '((systems . ("x86_64-linux")))))
         (job (and (pair? jobs) (car jobs)))
         (name (and job (assoc-ref job #:job-name)))
         (drv (and job (assoc-ref job #:derivation))))
    (unless (and (= (length jobs) 1)
                 (equal? name "wsm-live-minimal-image.x86_64-linux")
                 (string? drv)
                 (> (string-length drv) 0))
      (error "Cuirass custom job did not produce the expected ISO derivation"
             jobs))))

;; Load the host fragment from the checkout root. local-file is intentionally
;; root-relative and the service must use the pinned Cuirass record type.
(primitive-load "ci/cuirass/service.scm")
(unless (and (service? wsm-cuirass-service)
             (cuirass-configuration?
              (service-value wsm-cuirass-service)))
  (error "WSM Cuirass service fragment did not construct a pinned service"))

(display "WSM-SOURCE-MODULE-EVAL-OK ")
(display (length %wsm-performance-services))
(display " services, channel package: ")
(display (package-name wsm-tools))
(display " ")
(display (package-version wsm-tools))
(newline)
(display "WSM-CUIRASS-IMAGE-JOB-EVAL-OK: ISO derivation generated, not built")
(newline)
(display "WSM-CUIRASS-SERVICE-EVAL-OK")
(newline)
