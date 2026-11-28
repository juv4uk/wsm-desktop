;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Evaluate WSM Scheme modules and the Cuirass service/job against the exact
;; official Guix revision in channels.lock.scm.
;;
;; This uses the local Guix daemon to lower the image to a derivation. It does
;; not build the ISO, boot it, write to a disk, or authenticate the WSM channel.
;; WSM channel authentication requires the owner's signed Phase B bootstrap.
;;
;; scripts/check_scheme_module_coverage.py enforces complete wsm/ coverage.
(use-modules (guix packages)
             (guix store)
             (gnu services)
             ((ci cuirass images) #:select (cuirass-jobs))
             (wsm systems performance)
             (wsm packages wsm))

(unless (and (list? %wsm-performance-services)
             (pair? %wsm-performance-services))
  (error "WSM performance module exported no service definitions"))

(unless (package? wsm-tools)
  (error "WSM package module did not export a package record for wsm-tools"))

(unless (procedure? cuirass-jobs)
  (error "Cuirass custom job module did not export cuirass-jobs"))

;; Exercise the actual custom-job callback. image->job must resolve the pinned
;; image APIs and lower the ISO expression to a derivation, without building it.
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

;; Evaluate the real host service declaration. This catches Guix service-module,
;; configuration-field, and source-relative local-file errors.
(primitive-load "ci/cuirass/service.scm")
(unless (service? wsm-cuirass-service)
  (error "Cuirass service fragment did not define a Guix service"))

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
