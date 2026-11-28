;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Source-tree Guix API/evaluation check against the exact official Guix lock.
;; This does not exercise WSM channel lookup/authentication or start Cuirass.
;; The latter requires the owner's signed introduction and a dedicated run.
;;
;; Every module under wsm/ must be loaded here. The Cuirass helper is outside
;; the public wsm/ namespace, but its imports must also match the pinned Guix.
;; scripts/check_scheme_module_coverage.py enforces wsm/ module coverage.
(use-modules (guix packages)
             (wsm systems performance)
             (wsm packages wsm)
             ((ci cuirass images) #:select (cuirass-jobs)))

(unless (and (list? %wsm-performance-services)
             (pair? %wsm-performance-services))
  (error "WSM performance module exported no service definitions"))

(unless (package? wsm-tools)
  (error "WSM package module did not export a package record for wsm-tools"))

(unless (procedure? cuirass-jobs)
  (error "Cuirass custom job module did not export cuirass-jobs"))

(display "WSM-SOURCE-MODULE-EVAL-OK ")
(display (length %wsm-performance-services))
(display " services, channel package: ")
(display (package-name wsm-tools))
(display " ")
(display (package-version wsm-tools))
(display ", Cuirass module loaded against pinned Guix")
(newline)
