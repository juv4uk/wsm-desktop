;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Run Cuirass on a separate Guix build host.
;; This is a service fragment, not a full WSM host-system declaration.
;; The UI remains bound to loopback; remote access needs an authenticated proxy.
;; This service does not publish NARs or create signing keys.

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
           (channels (list #$%wsm-guix-channel #$%wsm-channel)))
          (specification
           (name 'h170-free-upstream-packages)
           (priority 1)
           (build '(custom (ci cuirass h170-free-packages)))
           (channels (list #$%wsm-guix-channel #$%wsm-channel)))))

(define wsm-cuirass-service
  (service cuirass-service-type
           (cuirass-configuration
            (host "localhost")
            (port 8081)
            ;; Keep building locally when no trusted substitute is available.
            (fallback? #t)
            (specifications %wsm-cuirass-specs))))
