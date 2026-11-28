;; SPDX-License-Identifier: LicenseRef-Volnist
;;;
;;; Cuirass jobset для WSM Desktop.
;;;
;;; Навіщо: оцінювання профілів у CI (`.github/workflows/guix-profile-evaluation.yml`)
;;; коштує 20+ хвилин і не дає нічого, крім «деривації обчислюються». Cuirass
;;; будує ті самі деривації й **віддає їх як substitutes**, тобто наступні
;;; прогони не компілюють те саме вдруге.
;;;
;;; Межа: цей файл — специфікація, а не доказ. Поки не прогнано
;;; `cuirass register --specifications` на машині з Guix, він нічого не
;;; доводить. Тому в репозиторії він позначений як NOT_RUN, а тест
;;; `tests/test_cuirass_specification.py` перевіряє лише його структуру.
;;;
;;; Використання (на машині з Guix):
;;;   cuirass register --specifications etc/cuirass/wsm-desktop.scm
;;;   cuirass web --host=127.0.0.1 --port=8081
;;;
;;; Публікація substitutes:
;;;   guix publish --port=3000 --cache=/var/cache/guix/publish
;;;   # клієнтам: --substitute-urls=http://<host>:3000

(use-modules (guix channels)
             (guix store)
             (guix monads)
             (ice-9 match))

;; Точні входи: pinned Guix плюс цей репозиторій. Рухомі гілки тут заборонені —
;; інакше «зелений» Cuirass не буде стосуватися жодного конкретного коміту.
(define %wsm-inputs
  (list (channel
         (name 'guix)
         (url "https://git.savannah.gnu.org/git/guix.git")
         (branch "master"))
        (channel
         (name 'wsm)
         (url "https://github.com/juv4uk/wsm-desktop.git")
         (branch "main"))))

(define %wsm-systems
  "x86_64-linux")

;; Системні деривації, які ми справді хочемо мати зібраними.
;;
;; `minimal` і `desktop` — Free-профілі, без Nonguix. `compatibility` свідомо
;; **не** входить: він тягне nonfree, а Cuirass-джобсет Free-каналу не має його
;; публікувати. Це та сама межа, що й у `channels/free.scm`.
(define %wsm-specifications
  (list
   (specification
    (name "wsm-free")
    (priority 1)
    (build '(channels wsm))
    (channels %wsm-inputs)
    (systems (list %wsm-systems)))))

%wsm-specifications
