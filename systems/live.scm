;; SPDX-License-Identifier: LicenseRef-Volnist
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
             (gnu system locale)
             (gnu services)
             (gnu services shepherd)
             (gnu services desktop)
             (gnu services networking)
             (gnu services sddm)
             (gnu packages fonts)
             (gnu packages kde-plasma)
             (wsm packages wsm))

;; Завантажуємо сусідній файл за абсолютним шляхом, а не через include з
;; відносним: тоді результат не залежить від того, з якого каталогу запущено
;; guix. current-filename дає шлях до цього файлу під час читання.
(define base-os
  (load (string-append (dirname (current-filename)) "/desktop.scm")))

;; Acceptance for the live image is a serial marker, not "it built". Without a
;; marker the only thing a boot smoke test can say is "QEMU exited".
;;
;; The service writes once, after user processes are up, and never fails the
;; boot: if the console is missing, the marker is simply absent, and the
;; verifier reports a missing marker instead of a broken system.
(define wsm-live-ready-marker
  (simple-service 'wsm-live-ready shepherd-root-service-type
    (list (shepherd-service
           (documentation "Announce on the serial console that the live system is up.")
           (provision '(wsm-live-ready))
           (requirement '(user-processes))
           (respawn? #f)
           (start #~(lambda ()
                      (catch #t
                        (lambda ()
                          (call-with-output-file "/dev/console"
                            (lambda (port)
                              (display "WSM_LIVE_READY" port)
                              (newline port)
                              (force-output port))))
                        (lambda _ #f))
                      #t))
           (stop #~(const #t))))))

(operating-system
  (inherit base-os)

  ;; Ті самі служби, що й у цільовому профілі, плюс наші інструменти.
  (packages
   (cons* wsm-tools
          font-dejavu
          font-liberation
          font-google-noto
          (operating-system-packages base-os)))

  ;; У live-сесії немає сенсу тримати повний набір локалей у пам'яті.
  (locale-definitions
   (list (locale-definition (name "uk_UA.utf8") (source "uk_UA"))
         (locale-definition (name "en_US.utf8") (source "en_US"))))

  ;; Ядро без тихих параметрів: якщо live-образ не стартує, причину має бути
  ;; видно на консолі, а не вгадано. console=ttyS0 потрібен і для маркера.
  (kernel-arguments '("console=ttyS0,115200"))

  (services
   (append (list wsm-live-ready-marker)
           (operating-system-services base-os))))
