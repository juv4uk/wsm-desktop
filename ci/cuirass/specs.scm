;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass specifications for WSM Desktop.
;;
;; The official Guix channel is pinned to the same Guix commit as the free
;; release lock. The WSM channel intentionally tracks main as a development
;; lane; its resolved commit is therefore different from a release's immutable
;; WSM source pin and must be recorded for each evaluation.
;;
;; Keep normal channel authentication enabled. Do not register this jobset until
;; owner-controlled WSM channel Phase B has been completed and verified with
;; guix git authenticate. These specs are not proof of channel trust.
;;
;; Cuirass builds derivations. It does not boot images, run the installer, or
;; publish WSM outputs as substitutes. See docs/CUIRASS.md for the boundaries.

(list
 ;; The channel's own tool package: a focused package derivation check.
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
          (branch "main")))))

 ;; The same live-minimal system profile used by scripts/build_iso.sh.
 ;; This is a rolling development job, not an immutable release reproduction.
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
          (branch "main"))))))
