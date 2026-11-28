;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Run Cuirass on a dedicated Guix build host after WSM channel trust Phase B.
;;
;; This is a fragment, not a full operating-system declaration: add this
;; service to the host's reviewed services list. Keep the web UI on localhost.
;; The local Cuirass service does not publish its build results as substitutes;
;; publishing is a separate service/security decision.

(use-modules (gnu services cuirass)
             (guix gexp)
             (ice-9 ftw))

;; Resolve the sibling spec file relative to this fragment, not the caller's
;; working directory. Embed it in the system closure.
(define %wsm-cuirass-specs-path
  (string-append (dirname (current-filename)) "/specs.scm"))

(define %wsm-cuirass-specs-file
  (local-file %wsm-cuirass-specs-path "wsm-cuirass-specs.scm"))

(define %wsm-cuirass-specs
  #~(load #$%wsm-cuirass-specs-file))

(define wsm-cuirass-service
  (service cuirass-service-type
           (cuirass-configuration
            ;; Loopback only. Expose through an authenticated reverse proxy
            ;; only after a separate deployment/security review.
            (host "localhost")
            (port 8081)
            (fallback? #t)
            (specifications %wsm-cuirass-specs))))
