;; SPDX-License-Identifier: GPL-3.0-or-later
;;
;; WSM Desktop — live-профіль для завантажувального ISO.
;;
;; СТАТУС: не зібрано й не перевірено (у середовищі написання немає Guix і
;; QEMU). Збирати на машині з Guix:
;;
;;     guix system image --image-type=iso9660 systems/live.scm
;;
;; Що це дає: завантажувальний ISO з KDE Plasma і нашими інструментами
;; (wsm-hwcheck, wsm-install, wsm-guix-deploy) усередині.
;;
;; Чого це НЕ дає: автоматичного встановлення. Установлення на диск — окремий
;; крок, який користувач виконує свідомо: wsm-guix-deploy готує конфігурацію,
;; далі guix system init. Автоматизувати цей крок означає реалізувати APPLY з
;; docs/INSTALLER-HANDOFF.md, і цього поки немає.
;;
;; ПЕРЕД ЗБИРКОЮ: задайте пароль для користувача wsm. У профілі його немає
;; навмисно — порожній пароль у живому образі це відкриті двері, а
;; захардкоджений пароль гірший за відсутній. Додайте (password ...) у
;; user-account або входьте через root у консолі.

(use-modules (gnu)
             (gnu services desktop)
             (gnu services networking)
             (gnu services sddm)
             (gnu packages fonts)
             (gnu packages kde-plasma)
             (wsm packages wsm))

(define base-os (include "desktop.scm"))

(operating-system
  (inherit base-os)

  ;; Ті самі служби, що й у цільовому профілі, плюс наші інструменти.
  (packages
   (cons* wsm-tools
          font-dejavu
          font-liberation
          font-noto
          (operating-system-packages base-os)))

  ;; У live-сесії немає сенсу тримати повний набір локалей у пам'яті.
  (locale-definitions
   (list (locale-definition (name "uk_UA.utf8") (source "uk_UA"))
         (locale-definition (name "en_US.utf8") (source "en_US"))))

  ;; Ядро без тихих параметрів: якщо live-образ не стартує, причину має бути
  ;; видно на консолі, а не вгадано.
  (kernel-arguments '("console=ttyS0,115200")))
