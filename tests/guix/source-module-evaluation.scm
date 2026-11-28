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


;; Cuirass API check against the exact Guix lock. This imports the custom module
;; from ci/cuirass/images.scm without registering a jobset or authenticating WSM.
(define %wsm-cuirass-service-smoke
  (service cuirass-service-type
          (cuirass-configuration (specifications #~'())))

(unless (and (procedure? arguments->systems)
             (procedure? image->job)
             (procedure? cuirass-jobs)
             (cuirass-configuration? (cuirass-configuration))
             %wsm-cuirass-service-smoke)
  (error "Pinned Guix Cuirass API or WSM image-job module is unavailable"))

(display "WSM-CUIRASS-API-EVAL-OK")
(newline)

(display "WSM-SOURCE-MODULE-EVAL-OK ")
(display (length %wsm-performance-services))
(display " services, channel package: ")
(display (package-name wsm-tools))
(display " ")
(display (package-version wsm-tools))
(newline)
