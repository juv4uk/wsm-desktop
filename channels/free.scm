;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Free channel set.
;;
;; До 28.11.2026 цей файл повертав лише %default-channels, тобто жоден
;; WSM-пакет не був досяжний через власний Free-набір: опублікований канал
;; існував, але його не було в тому, що споживач реально підключає.
;;
;; Тепер набір = upstream Guix плюс WSM. WSM-канал без introduction, доки
;; власник не підпише — це видно з channels/wsm.scm і docs/GUIX-CHANNEL.md.
;; Практичний наслідок: `guix pull` попередить, що канал не автентифікований;
;; збірка від цього не ламається, але й довіри не додає.
;;
;; Зафіксувати точний зріз:
;;   guix describe -f channels > channels.lock.scm

(use-modules (guix channels))

;; WSM іде ПІСЛЯ upstream, щоб його пакунки не могли підмінити базові.
(append %default-channels
        (list (channel
               (name 'wsm)
               (url "https://github.com/juv4uk/wsm-desktop")
               (branch "main"))))
