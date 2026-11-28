;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass host service fragment. The job specifications are supplied as an
;; explicit, root-owned source file and captured immutably in the Guix store.
;; This fragment does not register a WSM channel or publish substitutes.

(use-modules (gnu services)
             (gnu services cuirass)
             (guix gexp))

(define %wsm-cuirass-specs-source
  (local-file "/etc/guix/wsm/ci/cuirass/specs.scm"
              "wsm-cuirass-specs.scm"))

(define %wsm-cuirass-specs
  #~(load #$%wsm-cuirass-specs-source))

(define wsm-cuirass-service
  (service cuirass-service-type
           (cuirass-configuration
            (host "localhost")
            (port 8081)
            (fallback? #t)
            (specifications %wsm-cuirass-specs))))
