;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass service fragment for a dedicated WSM build host.
;;
;; This is not part of the WSM desktop/live system. It is added to the
;; services list of a separate Guix System build host.
;;
;; cuirass-service-type lives in (gnu services cuirass). The pinned
;; cuirass-configuration has no use-substitutes? field; substitutes are
;; controlled by the Guix daemon and fallback? controls local build fallback.
;;
;; Keep this job list narrow. A generic (channels wsm) build would enumerate
;; every WSM package; do not enable it until issue #367 is resolved and an
;; explicit package allowlist is approved. Substitute publication is separate.

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
  ;; Development input only; not an owner-authenticated release lock.
  (channel
   (name 'wsm)
   (url "https://github.com/juv4uk/wsm-desktop")
   (branch "main")))

(define %wsm-cuirass-specs
  #~(list
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
            (fallback? #t)
            (specifications %wsm-cuirass-specs))))
