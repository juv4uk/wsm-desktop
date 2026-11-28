;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass specifications for WSM Desktop.
;;
;; Cuirass is GNU Guix's own continuous integration server. Its value here is
;; not "another CI": it schedules and records derivation builds on a Guix host
;; using the pinned official Guix channel. It does not expose build outputs as
;; substitutes by itself. Sharing them with other machines requires a separately
;; operated publisher/remote server, signing-key custody and client trust; none
;; of those are configured by this jobset. GitHub Actions independently builds
;; the H170 allowlist in an ephemeral runner and performs QEMU acceptance.
;;
;; What it does NOT do: boot the image. Cuirass has no QEMU acceptance step, so
;; a green Cuirass job says "the closure builds", never "the medium boots".
;; docs/CUIRASS.md keeps that boundary explicit.
;;
;; Register with:
;;   cuirass register --specifications=ci/cuirass/specs.scm \
;;                    --database="dbname=cuirass host=/var/run/postgresql"
;;
;; The file must evaluate to a plain list of specifications: `cuirass register'
;; loads it and takes the last expression, so a gexp would not work here. The
;; gexp form belongs only in `cuirass-configuration'.

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

 ;; The live image derivation. Cuirass builds the same expression the release
 ;; workflow builds, so a broken profile shows up here within one poll interval
 ;; instead of after a forty-minute Actions run.
 (specification
  (name 'wsm-live-minimal-image)
  (priority 1)
  (build '(custom (ci cuirass images)))
  (channels (list %wsm-guix-channel %wsm-channel)))

 ;; Build the fixed upstream-only H170 Free package set. The custom job resolves
 ;; one package derivation per manifest root; it does not publish NARs.
 (specification
  (name 'h170-free-upstream-packages)
  (priority 1)
  (build '(custom (ci cuirass h170-free-packages)))
  (channels (list %wsm-guix-channel %wsm-channel))))
