;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM channel set: the official Guix channel plus this repository as a channel.
;;
;; СТАН: WSM канал не автентифікований. Він не має власного introduction.
;; Без owner-signed introduction-коміту, .guix-authorizations і keyring-гілки
;; звичайний Guix має відмовити в автентифікації цього каналу.
;;
;; Офіційний канал Guix явно закріплений за рухомою гілкою master і має
;; canonical introduction GNU Guix. Не використовуйте branch #f тут: без
;; commit pin це не floating branch, і Guix не може визначити channel commit.
;;
;; Діагностичні команди:
;;
;;   guix time-machine -C channels/wsm.scm -- describe -f channels
;;   guix time-machine -C channels/wsm.scm --disable-authentication -- describe -f channels
;;
;; Друга команда вимикає authentication і ніколи не є production/release gate.
;; Її результат повинен залишатися WSM_CHANNEL_AUTHENTICATION=NOT_TESTED.

(list
 ;; Офіційний GNU Guix channel; introduction збігається з channels.lock.scm.
 (channel
  (name 'guix)
  (url "https://git.guix.gnu.org/guix.git")
  (branch "master")
  (introduction
   (make-channel-introduction
    "9edb3f66fd807b096b48283debdcddccfea34bad"
    (openpgp-fingerprint
     "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA"))))

 ;; WSM — рухома гілка main без introduction до завершення owner trust bootstrap.
 (channel
  (name 'wsm)
  (url "https://github.com/juv4uk/wsm-desktop")
  (branch "main")))
