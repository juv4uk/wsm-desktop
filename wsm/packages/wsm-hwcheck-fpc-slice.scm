;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — пакет для зрізу wsm-hwcheck на Free Pascal.
;;
;; СТАТУС: не зібрано й не перевірено (у середовищі написання немає ні Guix,
;; ні FPC). Перед використанням:
;;   guix build -L . -f wsm/packages/wsm-hwcheck-fpc-slice.scm
;;
;; Навіщо окремий пакет, а не ще один бінарник у (wsm packages fpc-tools):
;; fpc-tools ставить wsm-hwcheck, який читає саму лише ідентичність PCI і не
;; має ні режиму завантаження, ні BIOS, ні CLI. Цей зріз додає рівно три групи
;; фактів і командний рядок. Два бінарники з однаковою назвою в одному store
;; були б гіршими за два пакети з різними назвами.
;;
;; Чому trivial-build-system: у tools/pascal/ немає configure, а
;; gnu-build-system додав би configure, make та validate-runpath, які тут
;; нічого не перевіряють. Компілятор викликається один раз у фазі 'build.
;;
;; Прапорці — ті самі, що в tools/pascal/Makefile (-Mobjfpc -Sh -O2): без -Sh
;; директива {$H+} ігнорується і рядки обрізаються на першому байті >127.

(define-module (wsm packages wsm-hwcheck-fpc-slice)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix build-system trivial)
  #:use-module (gnu packages pascal)
  #:use-module (wsm licenses)
  ;; `any` походить із SRFI-1, `string-contains` — із SRFI-13. Обидва
  ;; використовуються в предикаті select? нижче; без цих імпортів модуль
  ;; узагалі не завантажується, і помилка з'являється лише під час
  ;; обчислення Guix.
  #:use-module (srfi srfi-1)
  #:use-module (srfi srfi-13)
  #:export (wsm-hwcheck-fpc-slice))

(define-public wsm-hwcheck-fpc-slice
  (package
    (name "wsm-hwcheck-fpc-slice")
    (version "0.1.0-fpc-slice.1")
    ;; Відносні шляхи в local-file обчислюються від цього файлу, тому "../.."
    ;; — корінь репозиторію. select? не дає втягнути .git і результати збірки
    ;; у store: інакше source відрізнявся б між клонами й збірка перестала б
    ;; бути відтворюваною.
    (source (local-file "../.." "wsm-desktop-fpc-slice-source"
                        #:recursive? #t
                        #:select? (lambda (path _stat)
                                    (not (any (lambda (skip)
                                                (string-contains path skip))
                                              '("/.git" "/__pycache__" "/build"))))))
    (build-system trivial-build-system)
    (arguments
     (list
      #:modules '((guix build utils))
      #:phases
      #~(modify-phases %standard-phases
          (replace 'build
            (lambda* (#:key inputs #:allow-other-keys)
              (let ((fpc (search-input-file inputs "/bin/fpc")))
                ;; -O2 — узгоджений рівень оптимізації порту.
                ;; -Mobjfpc -Sh — режим і ANSI-рядки, як у tools/pascal/Makefile.
                ;; -FE — каталог, куди компілятор кладе бінарник.
                (invoke fpc "-O2" "-Mobjfpc" "-Sh" "-FE." "-owsw-hwcheck-slice"
                        "tools/pascal/wsm_hwcheck_slice.lpr")
                ;; Компілятор, який нічого не створив, не є успішною збіркою.
                (unless (file-exists? "wsm-hwcheck-slice")
                  (error "fpc returned success but produced no wsm-hwcheck-slice")))))
          (add-after 'build 'install
            (lambda* (#:key outputs #:allow-other-keys)
              (let* ((out (assoc-ref outputs "out"))
                     (bin (string-append out "/bin")))
                (mkdir-p bin)
                (copy-file "wsm-hwcheck-slice"
                           (string-append bin "/wsm-hwcheck-slice"))
                ;; copy-file не обіцяє зберегти біти виконання.
                (chmod (string-append bin "/wsm-hwcheck-slice") #o555)))))))
    ;; Єдина залежність збірки — компілятор. Бінарник не потребує FPC у час
    ;; виконання, тому fpc — native-input, а не propagated-input.
    (native-inputs (list fpc))
    (synopsis "Read-only hardware evidence collector, first Free Pascal slice")
    (description
     "The first vertical slice of the WSM hardware preflight collector written in
Free Pascal, with the command-line front end the Python collector has.  It reads
sysfs and procfs only and reports three fact groups: the boot mode (EFI directory
plus x86 DMI identity), the GPU record (PCI vendor and device ids, the bound
kernel driver, boot_vga, DRM card nodes and the PCIe link) and the DMI BIOS
release and date.  Every fact no readable source provided is listed in an
@code{unavailable} array instead of being defaulted.

This package is additive and is not a replacement for @code{wsm-tools}.  The
Python collector remains the shipped implementation until the parity check
against the same synthetic sysfs fixtures passes.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license wsm-license)))

;; `guix build -f FILE' uses the value of the file's LAST expression, and
;; `define-public' returns #<unspecified>. Naming the package here is what makes
;;     guix build -L . -f wsm/packages/wsm-hwcheck-fpc-slice.scm
;; work at all: without it the build fails with "#<unspecified>: not something we
;; can build". The line is inert when the file is loaded as a module by
;; tests/guix/source-module-evaluation.scm.
wsm-hwcheck-fpc-slice
