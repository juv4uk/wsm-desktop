;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Service fragment for a separate host that runs WSM's Cuirass instance.
;;
;; This file is intentionally a fragment, not a second host operating-system
;; definition. The adjacent specs.scm is captured in the store with local-file,
;; so the service does not depend on an undeclared /run/current-system path.
;;
;; Keep the web UI on loopback. The Cuirass UI does not provide authentication.
;; This service does not publish build results as substitutes; that requires a
;; separate remote-worker/publisher design and signing-key policy.

(use-modules (gnu services)
             (gnu services cuirass)
             (guix gexp))

(define %wsm-cuirass-specs-file
  (local-file "specs.scm" "wsm-cuirass-specs.scm"))

(define %wsm-cuirass-specs
  #~(load #$%wsm-cuirass-specs-file))

(define wsm-cuirass-service
  (service cuirass-service-type
           (cuirass-configuration
            (host "localhost")
            (port 8081)
            ;; This is a valid pinned-Guix field. Substitute lookup is handled
            ;; by the Guix daemon; there is no use-substitutes? field here.
            (fallback? #t)
            (specifications %wsm-cuirass-specs))))
