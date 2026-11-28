;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Run Cuirass on your own machine, with the WSM specifications.
;;
;; This is a fragment, not a full operating-system declaration: paste the
;; `services' entry into the system that should host the build farm. A complete
;; system definition would become a second source of truth for how WSM machines
;; are configured.
;;
;; Two corrections over the first revision of this file:
;;   * `cuirass-service-type' lives in `(gnu services cuirass)', not
;;     `(gnu services ci)' - the latter holds Laminar and Forgejo;
;;   * `cuirass-configuration' has no `use-substitutes?' field; substitutes are
;;     controlled by the daemon and by `fallback?'.
;;
;; The specifications are inlined as a gexp rather than loaded from a path: the
;; service writes them into a build sandbox, where /run/current-system does not
;; exist.

(use-modules (gnu services cuirass)
             (gnu services)
             (guix channels))

(define %wsm-guix-channel
  (channel
   (name 'guix)
   (url "https://git.guix.gnu.org/guix.git")
   (branch #f)
   (commit "4e5195be20d9b124df8a8bb69213412236e4668e")
   (introduction
    (make-channel-introduction
     "9edb3f66fd807b096b48283debdcddccfea34bad"
     (openpgp-fingerprint
      "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA")))))

(define %wsm-channel
  (channel
   (name 'wsm)
   (url "https://github.com/juv4uk/wsm-desktop")
   (branch "main")))

(define %wsm-cuirass-specs
  #~(list (specification
           (name 'wsm-channel)
           (priority 1)
           (build '(channels wsm))
           (channels (list #$%wsm-guix-channel #$%wsm-channel)))
          (specification
           (name 'wsm-live-minimal-image)
           (priority 1)
           (build '(custom (ci cuirass images)))
           (channels (list #$%wsm-guix-channel #$%wsm-channel)))))

(define wsm-cuirass-service
  (service cuirass-service-type
           (cuirass-configuration
            (host "localhost")
            (port 8081)
            ;; Keep building locally when a substitute is missing, rather than
            ;; failing the job.
            (fallback? #t)
            (specifications %wsm-cuirass-specs))))
