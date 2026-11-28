;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass specifications for WSM Desktop.
;;
;; The Guix input is pinned to the same commit as channels.lock.scm. The WSM
;; input tracks branch main for continuous development, so each evaluation
;; resolves a moving WSM revision: this is not an immutable release input.
;; Record the actual Guix/WSM commit pair with every release build.
;;
;; Cuirass builds package and ISO derivations. It does not boot the image and
;; this specification does not configure a substitute server. BIOS/UEFI guest
;; acceptance and any substitute publication remain separate release/deployment
;; responsibilities.
;;
;; Register only after WSM channel trust Phase B is complete:
;;   cuirass register --specifications=ci/cuirass/specs.scm \
;;                    --database="dbname=cuirass host=/var/run/postgresql"
;;
;; The WSM job module is (ci cuirass images), matching ci/cuirass/images.scm.

(list
 ;; The channel's own tool package.
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

 ;; The Minimal Live ISO derivation. The WSM source is main's head at the time
 ;; of each evaluation, not a signed or immutable release pin.
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
