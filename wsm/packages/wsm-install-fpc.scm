;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — read-only installer front end, Free Pascal implementation.
;;
;; СТАТУС: визначення пакета написане, але НЕ зібране в середовищі, де його
;; писали: там немає ні Guix, ні fpc. Твердження «збирається» тут не робиться.
;; Перевірка — .github/workflows/fpc-install-cli.yml, який виконує саме цю
;; збірку, а потім порівнює коди виходу з Python CLI.
;;
;; Перед використанням вручну:
;;   guix build -L . -f wsm/packages/wsm-install-fpc.scm
;;
;; Механіка збірки та сама, що в сусідньому (wsm packages fpc-tools): джерело —
;; корінь репозиторію з відсіюванням .git/__pycache__/build, компіляція через
;; tools/pascal/Makefile, fpc з (gnu packages pascal), install-file в $out/bin.
;; Один бінарник, без обгортки: паритетний тест має виконувати саме зібраний
;; файл. Python не входить у замикання, fcl-json теж: розбір JSON власний
;; (tools/pascal/wsmjson.pas).

(define-module (wsm packages wsm-install-fpc)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix build-system gnu)
  #:use-module (gnu packages pascal)
  #:use-module (wsm licenses)
  ;; `any' is from SRFI-1 and `string-contains' from SRFI-13; select? uses both
  ;; and without the imports the module fails to load only when Guix evaluates it.
  #:use-module (srfi srfi-1)
  #:use-module (srfi srfi-13)
  #:export (wsm-install-fpc))

(define-public wsm-install-fpc
  (package
    (name "wsm-install-fpc")
    (version "0.1.0")
    (source (local-file "../.." "wsm-desktop-source-install-fpc"
                        #:recursive? #t
                        #:select? (lambda (path _stat)
                                    (not (any (lambda (skip)
                                                (string-contains path skip))
                                              '("/.git" "/__pycache__" "/build"))))))
    (build-system gnu-build-system)
    (arguments
     (list
      ;; The repository's tests need the repository (tests/, scripts/); they run
      ;; in CI, not in the package build.
      #:tests? #f
      #:make-flags
      #~(list (string-append "FPC=" #$(file-append fpc "/bin/fpc")))
      #:phases
      #~(modify-phases %standard-phases
          (delete 'configure)
          (replace 'build
            (lambda* (#:key make-flags #:allow-other-keys)
              ;; Only this target: the neighbouring hwcheck/classify programs
              ;; have their own package and must not be built twice.
              (apply invoke "make" "-f" "tools/pascal/Makefile"
                     "wsm-install-fpc" make-flags)))
          (replace 'install
            (lambda* (#:key outputs #:allow-other-keys)
              (let* ((out (assoc-ref outputs "out"))
                     (bin (string-append out "/bin")))
                (install-file "tools/pascal/wsm-install-fpc" bin)
                ;; install-file does not promise the executable bit.
                (chmod (string-append bin "/wsm-install-fpc") #o555)))))))
    ;; gnu-build-system already provides make and the rest of the standard
    ;; inputs; fpc is the only addition.
    (native-inputs (list fpc))
    (synopsis "Read-only WSM installer front end, compiled with FPC")
    (description
     "Validates a WSM hardware report and reports whether the installer may
proceed, with the exit codes of the Python front end (0 accepted, 2 refused,
3 blocked on unresolved critical evidence).  The binary parses its own JSON,
selects the report schema version the document declares, and implements the
structural preflight rules that do not need a JSON Schema validator.  It does
not build the draft plan document, and every rule it does not implement is
listed in its source.  It never opens a block device, never spawns a process and
never requires root, so no interpreter, no site-packages and no schema library
enter the runtime closure.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license wsm-license)))
