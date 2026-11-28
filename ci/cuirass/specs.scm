;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass specifications for WSM Desktop.
;;
;; NOT_REGISTERABLE until the owner completes Guix channel Phase B:
;; signed introduction, .guix-authorizations, public keyring, and a tested
;; authenticated consumer path. The WSM commit below is deliberately an
;; invalid placeholder. Replace it only with the exact owner-approved,
;; authenticated WSM commit. Never use a moving branch or
;; --disable-authentication as a workaround.
;;
;; The job list is allowlisted. Cuirass builds/retains local outputs; publishing
;; substitutes is a separate service and is disabled until #367 and substitute
;; trust are cleared.

(list
 ;; Explicit WSM package allowlist. This remains unregistrable until Phase B
 ;; and the package-license gate #367 have been resolved.
 (specification
  (name "wsm-tools")
  (priority 1)
  (build '(packages "wsm-tools"))
  (channels
   (list (channel
          (name 'guix)
          (url "https://git.guix.gnu.org/guix.git")
          (branch #f)
          (commit "4e5195be20d9b124df8a8bb69213412236e4668e")
          (introduction
           (make-channel-introduction
            "9edb3f66fd807b096b48283debdcddccfea34bad"
            (openpgp-fingerprint
             "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA"))))
         (channel
          (name 'wsm)
          (url "https://github.com/juv4uk/wsm-desktop")
          (commit "OWNER_SIGNED_WSM_COMMIT_REQUIRED")))))

 ;; The live image derivation. Cuirass builds the same OS profile as the
 ;; release workflow, but does not perform BIOS/UEFI QEMU acceptance.
 (specification
  (name "wsm-live-minimal-image")
  (priority 1)
  (build '(custom (ci cuirass images)))
  (channels
   (list (channel
          (name 'guix)
          (url "https://git.guix.gnu.org/guix.git")
          (branch #f)
          (commit "4e5195be20d9b124df8a8bb69213412236e4668e")
          (introduction
           (make-channel-introduction
            "9edb3f66fd807b096b48283debdcddccfea34bad"
            (openpgp-fingerprint
             "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA"))))
         (channel
          (name 'wsm)
          (url "https://github.com/juv4uk/wsm-desktop")
          (commit "OWNER_SIGNED_WSM_COMMIT_REQUIRED"))))))
