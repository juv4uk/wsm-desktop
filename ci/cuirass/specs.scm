;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass specifications for WSM Desktop.
;;
;; Cuirass is GNU Guix's own continuous integration server. Its value here is
;; not "another CI": it builds *inside Guix*, on top of the exact channel lock
;; the release uses, and its results become substitutes. GitHub Actions builds
;; the image and boots it in QEMU; Cuirass proves the derivations actually build
;; from the pinned channels and warms the store for everyone else.
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
 ;; Every package the channel provides. This is the canonical Cuirass job and
 ;; it subsumes the single-package case: today the channel ships one package,
 ;; and when it ships three this job still covers them without an edit.
 (specification
  (name 'wsm-channel)
  (priority 1)
  (build '(channels wsm))
  (channels (list %wsm-guix-channel %wsm-channel)))

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
