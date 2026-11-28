;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass service fragment for a dedicated Guix build host.
;;
;; This is NOT a complete operating-system declaration and MUST NOT be deployed
;; until WSM's owner-signed channel authentication and the package/licensing
;; acceptance in issue #367 are complete.
;;
;; Cuirass schedules derivation builds through guix-daemon. It does not expose
;; a substitute server; guix publish is a separate service and is intentionally
;; not configured here.
;;
;; Evaluate this fragment from the wsm-desktop repository root so local-file
;; captures an immutable copy of the specifications in the system closure.

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
            ;; The pinned record has no use-substitutes? field. Keep its
            ;; conservative fallback default and do not configure a cache trust
            ;; policy here.
            (specifications #~(load #$%wsm-cuirass-specs)))))
