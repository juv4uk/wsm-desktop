;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; ШАБЛОН profile.scm для апаратного профілю. Не є профілем.
;;
;; Копіюйте в profiles/hardware/<vendor>/<model>/profile.scm лише тоді, коли є
;; native Linux evidence з цієї машини. Див. profiles/hardware/README.md:
;; відсутність профілю — чесний стан, синтетичний каталог — ні.
;;
;; Генератор доказів хешує ТОЧНІ байти цього файлу. Будь-яка правка після
;; збору доказів анулює bundle, тому спершу доведіть файл до фінального
;; вигляду, а вже потім запускайте scripts/draft_profile_evidence.py.
;;
;; Замініть кожне ЗАМІНИТИ. Не залишайте жодного в опублікованому профілі:
;; коментар із ЗАМІНИТИ в тому, що називається декларацією, — це обіцянка,
;; яку ніхто не перевіряв.

(use-modules (gnu)
             (gnu services)
             (gnu services base)
             (gnu services desktop)
             (gnu services networking)
             (gnu services shepherd)
             (gnu system nss)
             (gnu packages linux))

;; Варіант профілю. Один профіль — один активний GPU-драйвер.
;; Ніколи не змішуйте nouveau і пропрієтарний nvidia в одному boot profile.
;;   'free           — лише офіційний Guix, Linux-libre, upstream Mesa
;;   'compatibility  — додає Nonguix і пропрієтарний драйвер, явний opt-in
(define profile-variant 'free)

(operating-system
  (host-name "ЗАМІНИТИ")
  (timezone "ЗАМІНИТИ")
  (locale "ЗАМІНИТИ")

  ;; Ядро. Для 'free — linux-libre. Для 'compatibility — nongnu linux,
  ;; бо пропрієтарний модуль не збирається проти Linux-libre.
  (kernel linux-libre)

  ;; Аргументи ядра фіксують саме те, що перевірялося. Не додавайте сюди
  ;; прапорці «на всяк випадок»: кожен із них — частина доказу.
  (kernel-arguments '("quiet"))

  (initrd-modules '())

  (file-systems
   ;; ЗАМІНИТИ на реальні UUID з цієї машини. Не копіюйте чужі.
   (cons* (file-system
            (mount-point "/")
            (device (uuid "ЗАМІНИТИ" 'ext4))
            (type "ext4"))
          %base-file-systems))

  (users (cons* (user-account
                 (name "ЗАМІНИТИ")
                 (group "users")
                 (supplementary-groups '("wheel" "netdev" "audio" "video")))
                %base-user-accounts))

  (packages (append (list
                     ;; Мінімум, потрібний для повторної перевірки цього ж
                     ;; профілю на цій машині.
                     (specification->package "pciutils")
                     (specification->package "usbutils"))
                    %base-packages))

  (services
   (append (list
            (service network-manager-service-type)
            (service wpa-supplicant-service-type)
            ;; Desktop-сервіси додаються лише якщо профіль справді про
            ;; робочий стіл. Для headless-перевірки їх не потрібно.
            (service elogind-service-type))
           %base-services))

  ;; Мікрокод — окремий факт з окремим доказом. Для 'free він відсутній.
  (kernel-loadable-modules '())

  (name-service-switch %mdns-host-lookup-nss))
