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
;; The file is a plain list of specifications, as `cuirass register` expects;
;; the same list is used by the service definition in service.scm.

(list
 ;; The channel's own tool package: the smallest job that fails if the pinned
 ;; channels stop being able to build what we ship.
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

 ;; The live image derivation. Cuirass builds the same expression the release
 ;; workflow builds, so a broken profile shows up here within one poll interval
 ;; instead of after a forty-minute Actions run.
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
