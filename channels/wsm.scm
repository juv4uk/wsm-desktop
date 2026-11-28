;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM channel set: the official Guix channel plus this repository as a channel.
;;
;; Навіщо: доти всі збірки використовують `-L "$PWD"`, тобто дерево джерел
;; підкладається вручну. Це працює для збірки з репозиторію, але не є каналом:
;; сторонній користувач не може зробити `guix pull` і отримати (wsm packages wsm).
;;
;; СТАН: канал ще не автентифікований. У .guix-channel немає introduction, а
;; без підписаного introduction-коміту, .guix-authorizations і keyring-гілки
;; Guix відмовиться приймати цей канал без --disable-authentication.
;;
;; Тому цей файл — не «готовий канал», а точне місце, де видно різницю:
;;
;;   guix time-machine -C channels/wsm.scm -- describe      ; відмова: не автентифіковано
;;   guix time-machine -C channels/wsm.scm --disable-authentication -- describe
;;
;; Друга команда працює вже сьогодні й саме тому нею не користуються для
;; релізних збірок: вона вимикає рівно ту перевірку, яку проєкт обіцяє.
;;
;; Після trust bootstrap цей файл стає звичайним каналом без жодних прапорців.
;;
;; Формат той самий, що у channels.lock.scm: один вираз (list ...) без
;; use-modules. Guix оцінює channel-файли в контексті, де
;; make-channel-introduction і openpgp-fingerprint уже доступні, а структурний
;; чекер очікує рівно одну форму.

(list
 ;; Офіційний Guix — з тим самим introduction, що й у channels.lock.scm.
 (channel
  (name 'guix)
  (url "https://git.guix.gnu.org/guix.git")
  (branch "master")
  (introduction
   (make-channel-introduction
    "9edb3f66fd807b096b48283debdcddccfea34bad"
    (openpgp-fingerprint
     "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA"))))

 ;; WSM — без introduction, доки триває bootstrap.
 (channel
  (name 'wsm)
  (url "https://github.com/juv4uk/wsm-desktop")
  (branch "main")))
