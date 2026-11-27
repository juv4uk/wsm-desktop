;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Minimal channel-context evaluation. This is deliberately not an
;; authentication test: the WSM introduction/key bootstrap is owner-controlled.
(use-modules (wsm systems performance))

(unless (and (list? %wsm-performance-services)
             (pair? %wsm-performance-services))
  (error "WSM performance module exported no service definitions"))

(display "WSM-CHANNEL-MODULE-EVAL-OK ")
(display (length %wsm-performance-services))
(display " services\n")
