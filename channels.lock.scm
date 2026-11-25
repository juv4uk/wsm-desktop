;; SPDX-License-Identifier: GPL-3.0-or-later
;;
;; Authenticated Guix channel lock for WSM Hardware Preview RC1.
;; Generated from the isolated authenticated profile used for issue #39:
;;   guix pull --profile=<isolated> --url=https://git.guix.gnu.org/guix.git \
;;     --commit=4e5195be20d9b124df8a8bb69213412236e4668e
;;   guix describe -p <isolated> -f channels
;; Authentication was enabled; no --disable-authentication was used.
;; This is the free-only channel set: no Nonguix, no nonfree firmware,
;; no substitute server and no signing key are added here.

(list (channel
       (name 'guix)
       (url "https://git.guix.gnu.org/guix.git")
       (branch #f)
       (commit "4e5195be20d9b124df8a8bb69213412236e4668e")
       (introduction
        (make-channel-introduction
         "9edb3f66fd807b096b48283debdcddccfea34bad"
         (openpgp-fingerprint
          "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA")))))
