;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Окремий authenticated channel lock лише для WSM Compatibility.
;; Вільний channels.lock.scm залишається GNU Guix-only.
;;
;; Nonguix upstream introduction:
;;   commit 897c1a470da759236cc11798f4e0a5f7d4d59fbc
;;   key 2A39 3FFF 68F4 EF7A 3D29 12AF 6F51 20A0 22FB B2D5
;; Пінований Nonguix commit 6b8897cd6f3223b158c070cdc9cc638279f8c337
;; має перевірений підпис Jelle Licht; fingerprint підписанта
;; E31D 9DDE EBA5 4A14 8A20 4550 DA45 97F9 47B4 1025
;; присутній у .guix-authorizations цього каналу.
;;
;; Це лише pin джерел. Він не доводить build closure, працездатність GPU
;; або право на розповсюдження пропрієтарних бінарних компонентів.

(list
 (channel
  (name 'guix)
  (url "https://git.guix.gnu.org/guix.git")
  (branch #f)
  (commit "4e5195be20d9b124df8a8bb69213412236e4668e")
  (introduction
   (make-channel-introduction
    "9edb3f66fd807b096b48283debdcddccfea34bad"
    (openpgp-fingerprint
     "BBB0 2DDF 2CEA F6A8 0D1D E643 A2A0 6DF2 A33A 54FA"))))
 (channel
  (name 'nonguix)
  (url "https://gitlab.com/nonguix/nonguix")
  (branch #f)
  (commit "6b8897cd6f3223b158c070cdc9cc638279f8c337")
  (introduction
   (make-channel-introduction
    "897c1a470da759236cc11798f4e0a5f7d4d59fbc"
    (openpgp-fingerprint
     "2A39 3FFF 68F4 EF7A 3D29 12AF 6F51 20A0 22FB B2D5")))))
