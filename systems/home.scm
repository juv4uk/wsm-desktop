;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — користувацьке середовище.
;;
;; СТАТУС: не зібрано й не перевірено (у середовищі написання немає Guix).
;;
;; Навіщо окремий home-конфіг, якщо є system-конфіг:
;;
;; Звук у Guix — це per-user служба, а не системна. PipeWire запускається в
;; сеансі користувача, і саме там живе WirePlumber. Спроба зробити це системною
;; службою дає два звукові стеки, які борються за одне пристрій.
;;
;; Чому PipeWire, а не PulseAudio:
;;
;; У Plasma 6 аплет гучності й розділ «Звук» розмовляють PulseAudio-протоколом —
;; їм байдуже, хто саме його обслуговує. Але запис екрана (KWin) бере звук із
;; PipeWire-джерел, яких у старого демона немає, а Bluetooth-аудіо живе в
;; WirePlumber. Тому PipeWire з увімкненою емуляцією PulseAudio — це єдиний
;; варіант, де працює все: і аплет, і старий софт, і запис екрана.
;;
;; enable-pulseaudio? лишаємо #t (типове): без нього половина програм не побачить
;; звукового сервера взагалі.

(use-modules (gnu home)
             (gnu home services)
             (gnu home services desktop)
             (gnu home services sound)
             (gnu services)
             (gnu packages)
             (guix gexp))

(define %wsm-home-packages
  (specifications->packages
   (list
    ;; Те, без чого робочий стіл незручний, але що не є системним:
    "pavucontrol"        ; мікшер: без нього не видно, хто говорить у динамік
    "xdg-utils"          ; відкрити файл/посилання типовою програмою
    "xdg-desktop-portal"
    "xdg-desktop-portal-gtk")))

(home-environment
 (packages %wsm-home-packages)

 (services
  (list
   ;; dbus потрібен PipeWire і більшості десктопних програм.
   (service home-dbus-service-type)

   ;; PipeWire + WirePlumber + pipewire-pulse.
   ;; Служба стартує при вході, а не при завантаженні: звук — це сеанс.
   (service home-pipewire-service-type))))
