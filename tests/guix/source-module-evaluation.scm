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

;; The custom job body contains Guix CI helpers that are not evaluated simply
;; by importing the module. Resolve the exact bindings used by its first run.
(define cuirass-images-module (resolve-module '(ci cuirass images)))
(unless (procedure? (module-ref cuirass-images-module 'derivation->job))
  (error "Cuirass job module lacks the derivation->job binding from (gnu ci)"))
(unless (procedure? (module-ref cuirass-images-module '%graft?))
  (error "Cuirass job module lacks the %graft? parameter"))
(unless (procedure? (module-ref cuirass-images-module 'assq-ref))
  (error "Cuirass job module lacks the assq-ref binding"))

;; Invoke the actual Cuirass entry point. This lowers the ISO derivation through
;; Guix's image->job helper and validates the returned job record without
;; building the ISO payload.
(define cuirass-image-job-list
  (cuirass-jobs (open-connection) '((system . "x86_64-linux"))))
(unless (and (list? cuirass-image-job-list)
             (= (length cuirass-image-job-list) 1)
             (string=? (assq-ref (car cuirass-image-job-list) #:job-name)
                       "wsm-live-minimal.x86_64-linux")
             (string? (assq-ref (car cuirass-image-job-list) #:derivation)))
  (error "Cuirass custom job did not produce the expected x86_64 ISO job"))

;; Load the service fragment as a real Guix configuration to catch renamed
;; service modules/fields and validate its adjacent local-file reference.
(primitive-load "ci/cuirass/service.scm")
(unless (service? wsm-cuirass-service)
  (error "Cuirass service fragment did not define a Guix service"))

(display "WSM-CUIRASS-SERVICE-EVAL-OK")
(newline)
