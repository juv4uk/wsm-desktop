;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Source-tree Guix API/evaluation compatibility check against the exact
;; official Guix lock. This does not exercise WSM channel lookup/authentication
;; or start a Cuirass daemon.
;;
;; Every module under wsm/ must be loaded here. The Cuirass helper is outside
;; that public namespace, but its imports and service record must match the
;; exact Guix revision in channels.lock.scm.
(use-modules (guix packages)
             (guix store)
             (gnu services)
             (gnu services cuirass)
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

;; Load the real service fragment against the pinned Cuirass record type.
;; This catches wrong module imports, unsupported record fields and missing
;; store inputs without starting PostgreSQL or exposing an unauthenticated UI.
(primitive-load "ci/cuirass/service.scm")
(unless (and (service? wsm-cuirass-service)
             (cuirass-configuration?
              (service-value wsm-cuirass-service)))
  (error "WSM Cuirass service fragment did not construct a pinned service"))

;; Exercise the custom job entry point far enough to lower the ISO image to a
;; derivation. This proves the pinned image->job API, module imports, and profile
;; lookup all work; it deliberately does not build the resulting derivation.
(let* ((store (open-connection))
       (jobs (cuirass-jobs store '((systems . ("x86_64-linux"))))))
  (unless (= (length jobs) 1)
    (error "Cuirass WSM image job count is not one" jobs))
  (unless (string= (assq-ref (car jobs) '#:job-name)
                   "wsm-live-minimal-image.x86_64-linux")
    (error "Cuirass WSM image job name is unexpected" jobs)))

(display "WSM-SOURCE-MODULE-EVAL-OK ")
(display (length %wsm-performance-services))
(display " services, channel package: ")
(display (package-name wsm-tools))
(display " ")
(display (package-version wsm-tools))
(display ", pinned Cuirass service and image job evaluated")
(newline)
