;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass service fragment for a dedicated Guix build host.
;;
;; This is NOT a complete operating-system declaration and MUST NOT be deployed
;; until the WSM channel has owner-signed authentication and the job allowlist
;; has passed the licensing review in issue #367.
;;
;; Cuirass schedules Guix derivation builds through guix-daemon. This service
;; does not expose a substitute server; guix publish is a separate service and
;; is intentionally not configured here.
;;
;; Evaluate this fragment from the wsm-desktop repository root so local-file
;; can capture ci/cuirass/specs.scm in the system closure.

(use-modules (gnu services)
             (gnu services cuirass)
             (guix gexp))

(define %wsm-cuirass-specs
  (local-file "ci/cuirass/specs.scm" "wsm-cuirass-specs.scm"))

(define wsm-cuirass-service
  (service cuirass-service-type
           (cuirass-configuration
            ;; Keep the unauthenticated administration UI on loopback.
            ;; Use an authenticated TLS reverse proxy for remote administration.
            (host "localhost")
            (port 8081)
            ;; Local guix-daemon worker; no remote worker or substitute server.
            (fallback? #f)
            (specifications #~(load #$%wsm-cuirass-specs)))))
