;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass specifications for WSM Desktop.
;;
;; STATUS: NOT_REGISTERABLE until the owner completes WSM channel Phase B:
;; signed introduction/history, .guix-authorizations, public keyring and a
;; successful normal "guix git authenticate" consumer check.
;;
;; This file intentionally contains one image job only. Do not add a broad
;; (build '(channels wsm)) job or wsm-tools package job while issue #367's
;; license/package metadata decision is unresolved. No substitutes are served.

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

;; Deliberately not a valid commit. This placeholder prevents Cuirass from
;; treating a moving development branch as an authenticated production input.
(define %wsm-channel
  (channel
   (name 'wsm)
   (url "https://github.com/juv4uk/wsm-desktop")
   (branch #f)
   (commit "OWNER_SIGNED_WSM_COMMIT_REQUIRED")))

(list
 (specification
  (name 'wsm-live-minimal-image)
  (priority 1)
  (build '(custom (ci cuirass images)))
  (channels (list %wsm-guix-channel %wsm-channel))))
