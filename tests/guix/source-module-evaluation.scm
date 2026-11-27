;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Source-tree Guix API/evaluation compatibility check against the exact
;; official Guix lock. This does not exercise WSM channel lookup/authentication.
;; The latter requires the owner's signed introduction and a dedicated lock.
(use-modules (wsm systems performance))

(unless (and (list? %wsm-performance-services)
             (pair? %wsm-performance-services))
  (error "WSM performance module exported no service definitions"))

(display "WSM-SOURCE-MODULE-EVAL-OK ")
(display (length %wsm-performance-services))
(display " services\n")
