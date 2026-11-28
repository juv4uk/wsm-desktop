;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass specifications for WSM Desktop.
;;
;; Guix is pinned to the release lock. WSM main is a moving development input;
;; production registration remains gated on owner-signed channel Phase B.
;; Cuirass builds derivations only. It does not boot images or publish NARs.

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

(list
 ;; Evaluate/build all packages exposed by the WSM channel.
 (specification
  (name 'wsm-channel)
  (priority 1)
  (build '(channels wsm))
  (channels (list %wsm-guix-channel %wsm-channel)))

 ;; Build the same minimal live image used by the release workflow.
 (specification
  (name 'wsm-live-minimal-image)
  (priority 1)
  (build '(custom (ci cuirass images)))
  (channels (list %wsm-guix-channel %wsm-channel)))

 ;; Build only the upstream package roots selected for the owner's H170 Free
 ;; target. This is not a hardware profile and is not an artifact-publication
 ;; authorization. Firmware and WSM-owned package outputs are excluded.
 (specification
  (name 'h170-free-upstream-packages)
  (priority 1)
  (build '(custom (ci cuirass h170-free-packages)))
  (channels (list %wsm-guix-channel %wsm-channel))))
