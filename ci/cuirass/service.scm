;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Run Cuirass on your own machine, with the WSM specifications.
;;
;; This is a fragment, not a full operating-system declaration: paste the
;; `services' entry into the system that should host the build farm. It is
;; written as a fragment on purpose - a complete system definition would become
;; a second source of truth for how WSM machines are configured.
;;
;; What you get: a loopback-only web interface and PostgreSQL-backed job
;; history. The Guix daemon may consume its configured substitutes. This local
;; service does not publish its own outputs; QEMU boot acceptance stays in the
;; release workflow.

(use-modules (gnu services cuirass)
             (gnu services)
             (guix channels)
             (guix gexp))

(define %wsm-cuirass-specs-file
  ;; Capture the adjacent specs file in the store. Do not rely on an
  ;; unprovided /run/current-system/profile/share/wsm path.
  (local-file "specs.scm" "wsm-cuirass-specs.scm"))

(define %wsm-cuirass-specs
  ;; The CLI and the service use the same source file.
  #~(load #$%wsm-cuirass-specs-file))

(define wsm-cuirass-service
  (service cuirass-service-type
           (cuirass-configuration
            (host "localhost")
            (port 8081)
            ;; Dependency substitutes are controlled by the Guix daemon.
            ;; This local-daemon service does not publish its own outputs;
            ;; that needs separate remote workers and guix-publish configuration.
            (fallback? #t)
            (specifications %wsm-cuirass-specs))))
