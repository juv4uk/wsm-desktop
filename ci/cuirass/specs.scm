;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Narrow Cuirass specification for the WSM minimal live ISO.
;;
;; Do not add (build '(channels wsm)) here until the owner resolves the
;; LicenseRef-Volnist/package-metadata gate in issue #367 and approves an
;; explicit package allowlist. The custom live-image job is the only target
;; represented here; public substitute publication remains a separate gate.
;;
;; The file must evaluate to a plain list of specifications: cuirass register
;; loads it and takes the last expression. The service fragment builds the same
;; single specification as a gexp.

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
  ;; Development input only: owner-signed WSM channel bootstrap is not done.
  (channel
   (name 'wsm)
   (url "https://github.com/juv4uk/wsm-desktop")
   (branch "main")))

(list
 (specification
  (name 'wsm-live-minimal-image)
  (priority 1)
  (build '(custom (ci cuirass images)))
  (channels (list %wsm-guix-channel %wsm-channel))))
