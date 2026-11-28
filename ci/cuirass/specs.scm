;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass specifications for WSM Desktop.
;;
;; Cuirass is GNU Guix's native build coordinator. This file is an inert
;; prototype only: do not register it until the WSM channel has owner-controlled
;; authentication and the package allowlist/licensing gate in issue #367 is
;; resolved. Cuirass schedules derivation builds through guix-daemon; it does
;; not itself serve substitutes.
;;
;; What it does NOT do: boot the image. Cuirass has no QEMU acceptance step, so
;; a green Cuirass job says "the closure builds", never "the medium boots".
;; docs/CUIRASS.md keeps that boundary explicit.
;;
;; Do NOT run cuirass register yet. The WSM channel is not authenticated:
;; .guix-authorizations, owner-signed introduction and public keyring bootstrap
;; are still absent. The package allowlist also awaits issue #367.
;;
;; After owner Phase B and explicit package/license acceptance, register only
;; with authenticated channel inputs. The file is a plain list of specs; the
;; service fragment loads this file from the repository with local-file.

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
          ;; Deliberately tracks main for future CI polling. This is not an
          ;; authenticated/pinned release input until owner Phase B is complete.
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
