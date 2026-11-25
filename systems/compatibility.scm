;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — профіль Compatibility: пропрієтарний драйвер NVIDIA.
;;
;; СТАТУС: не зібрано й не перевірено (у середовищі написання немає Guix).
;;
;; Це НЕ частина вільного профілю. Профіль підключає Nonguix — незалежний
;; канал спільноти, який не є частиною офіційного GNU Guix (див. docs/ETHICS.md).
;; Кожен компонент тут nonfree, і користувач обирає його свідомо.
;;
;; Чому окремий файл, а не прапорець у desktop.scm: у Free-профілю не має бути
;; жодного шляху, який тягне Nonguix. Окремий файл робить це видно з першого
;; рядка, і tests/test_system_profiles.py перевіряє, що desktop.scm і live.scm
;; на Nonguix не посилаються.
;;
;; Чому SDDM, а не GDM: у Nonguix прямо сказано, що GDM із пропрієтарним
;; драйвером має відомі проблеми — не запускаються Wayland-сесії й буває чорний
;; екран на switchable graphics. desktop.scm уже прибирає GDM, тож цей профіль
;; лише передає sddm-service-type у конфігурацію Xorg.
;;
;; ЗБИРАТИ:
;;   guix time-machine -C channels.compatibility.lock.scm -L . -- system build systems/compatibility.scm
;;
;; Перед включенням драйвера в ISO перевірити право на розповсюдження: Nonguix
;; завантажує бінарники з NVIDIA, і це не те саме, що право покласти їх в образ.

(use-modules (gnu)
             (gnu services sddm)
             (nonguix transformations)
             (nongnu packages linux)
             (nongnu packages nvidia))

(define base-os
  (load (string-append (dirname (current-filename)) "/desktop.scm")))

;; nvda-580 — гілка драйвера, яка за таблицею підтримки Nonguix покриває від
;; Pascal (GeForce 10) до Blackwell. Для Pascal це остання гілка, що взагалі
;; підтримує ці карти пропрієтарним шляхом.
;;
;; configure-xorg? приймає тип служби дисплейного менеджера: без цього Xorg не
;; дізнається про модуль nvidia, і сесія не стартує.
(define nvidia-transform
  (nonguix-transformation-nvidia
   #:driver nvda-580
   #:configure-xorg? sddm-service-type))

(nvidia-transform
 (operating-system
  (inherit base-os)

  ;; linux-firmware потрібен частині периферії; він nonfree і живе лише тут.
  (firmware (cons* linux-firmware %base-firmware))

  (kernel-arguments
   (append '("modprobe.blacklist=nouveau")
           (operating-system-kernel-arguments base-os)))))
