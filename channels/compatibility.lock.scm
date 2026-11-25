;; SPDX-License-Identifier: GPL-3.0-or-later
;;
;; Authenticated Compatibility lock: Guix free snapshot + Nonguix 6b8897c.
;; Used for systems/live-compat.scm (NVIDIA 580.xx for Pascal GP107).
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
       (name 'nonguix)
       (url "https://gitlab.com/nonguix/nonguix")
       (branch #f)
       (commit "6b8897cd6f3223b158c070cdc9cc638279f8c337")
       (introduction
        (make-channel-introduction
         "897c1a470da759236cc11798f4e0a5f7d4d59fbc"
         (openpgp-fingerprint
          "2A39 3FFF 68F4 EF7A 3D29  12AF 6F51 20A0 22FB B2D5")))))
