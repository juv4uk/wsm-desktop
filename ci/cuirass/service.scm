;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Run Cuirass on your own machine, with the WSM specifications.
;;
;; This is a fragment, not a full operating-system declaration: paste the
;; `services' entry into the system that should host the build farm. It is
;; written as a fragment on purpose - a complete system definition would become
;; a second source of truth for how WSM machines are configured.
;;
;; What you get: a web interface on port 8081, a PostgreSQL-backed job history,
;; and substitutes for anything the jobs build. What you do not get: QEMU boot
;; acceptance. That stays in the release workflow.

(use-modules (gnu services ci)
             (gnu services)
             (guix channels))

(define %wsm-cuirass-specs
  ;; Loaded from the file so the CLI and the service cannot drift apart.
  #~(load "/run/current-system/profile/share/wsm/ci/cuirass/specs.scm"))

(define wsm-cuirass-service
  (service cuirass-service-type
           (cuirass-configuration
            (host "localhost")
            (port 8081)
            ;; Substitutes make a build farm useful; without them every job
            ;; rebuilds its whole closure from source.
            (use-substitutes? #t)
            (fallback? #t)
            (specifications %wsm-cuirass-specs))))
