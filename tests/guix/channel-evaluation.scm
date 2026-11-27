;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Minimal WSM channel module evaluation against the exact Guix lock.
;; This is not a channel-authentication test; the owner-controlled signed
;; introduction and authorization bootstrap are a separate release gate.
(use-modules (wsm systems performance))

(unless (and (list? %wsm-performance-services)
             (pair? %wsm-performance-services))
  (error "WSM performance module exported no service definitions"))

(display "WSM-CHANNEL-MODULE-EVAL-OK ")
(display (length %wsm-performance-services))
(display " services\n")
