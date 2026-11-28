;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass service helper for a dedicated Guix build host.
;;
;; This is not part of WSM desktop/live profiles. It deliberately accepts the
;; specifications gexp from the host configuration: no guessed profile path,
;; missing package installation, or implicit channel checkout is performed.
;; Do not add this service to a host until the WSM channel Phase B trust
;; bootstrap and the Cuirass specification gate have both passed.

(use-modules (gnu services)
             (gnu services cuirass))

(define (wsm-cuirass-service specifications)
  "Return the Cuirass service for a dedicated host.

SPECIFICATIONS must be an owner-approved gexp that evaluates to the reviewed,
allowlisted Cuirass specification list after WSM channel authentication."
  (service cuirass-service-type
           (cuirass-configuration
            (host "localhost")
            (port 8081)
            (fallback? #t)
            (specifications specifications))))
