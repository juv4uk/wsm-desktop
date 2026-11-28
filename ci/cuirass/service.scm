;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Service fragment for a separate Guix host.
;;
;; Evaluate this file from the root of the WSM checkout. Guix's pinned
;; local-file resolves relative paths against the current working directory,
;; not the directory of this Scheme file.

(use-modules (gnu services)
             (gnu services cuirass)
             (guix gexp))

(define %wsm-cuirass-specs-file
  (local-file "ci/cuirass/specs.scm" "wsm-cuirass-specs.scm"))

(define %wsm-cuirass-specs
  #~(load #$%wsm-cuirass-specs-file))

(define wsm-cuirass-service
  (service cuirass-service-type
           (cuirass-configuration
            (host "localhost")
            (port 8081)
            (fallback? #t)
            (specifications %wsm-cuirass-specs))))
