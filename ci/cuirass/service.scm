;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Service fragment for a machine that hosts the WSM Cuirass instance.
;;
;; Add wsm-tools to the host system packages. Its install phase places the
;; specification at /run/current-system/profile/share/wsm/ci/cuirass/specs.scm.
;; The Cuirass job module itself is resolved from the authenticated WSM channel
;; checkout; normal channel authentication must remain enabled.
;;
;; This fragment does not configure guix publish and does not expose build
;; products as public substitutes. It also does not provide QEMU acceptance.

(use-modules (gnu services ci)
             (gnu services))

(define %wsm-cuirass-specs
  #~(load "/run/current-system/profile/share/wsm/ci/cuirass/specs.scm"))

(define wsm-cuirass-service
  (service cuirass-service-type
           (cuirass-configuration
            (host "localhost")
            (port 8081)
            ;; Consume permitted substitutes for dependencies where available.
            ;; This does not publish WSM's own build results.
            (use-substitutes? #t)
            (fallback? #t)
            (specifications %wsm-cuirass-specs))))
