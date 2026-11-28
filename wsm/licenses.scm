;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Власна ліцензія WSM ВОЛЬНІСТЬ як обʼєкт Guix.
;;
;; Навіщо: package-визначення оголошували (license gpl3+), тоді як код під
;; LicenseRef-Volnist. Це #367. Варіант (a) — не маскування, а точність:
;; метадані кажуть те саме, що й заголовки файлів.
;;
;; SPDX: LicenseRef-Volnist — синтаксично правильний вираз (SPDX 2.3.1 Annex D,
;; license-ref). REUSE вимагає, щоб текст лежав у LICENSES/LicenseRef-Volnist.txt —
;; він там лежить.
;;
;; Guix не читає ліцензію під час збирання: package-license — це метадані.
;; guix lint перевіряє лише, що поле є <license> або списком таких, а guix show
;; друкує поле name. Тому власний запис нічого не ламає й не робить код вільнішим.

(define-module (wsm licenses)
  #:use-module (guix licenses)
  #:export (license-ref-volnist))

;; Конструктор `license` експортовано з (guix licenses) знову лише з червня 2026;
;; на старішому Guix він не зв'язаний, і тоді працює доступ через @@.
(define license
  (or (false-if-exception (@@ (guix licenses) license))
      (@@ (guix licenses) license)))

(define license-ref-volnist
  (license "LicenseRef-Volnist"
           "file://LICENSES/LicenseRef-Volnist.txt"
           (string-append
            "Власна ліцензія WSM ВОЛЬНІСТЬ. Не входить до списку SPDX, "
            "не схвалена OSI і не є ліцензією вільного ПЗ за FSF. "
            "Повний текст: LICENSES/LicenseRef-Volnist.txt.")))
