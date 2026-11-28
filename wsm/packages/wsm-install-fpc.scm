;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Desktop — read-only installer front end, Free Pascal implementation.
;;
;; СТАТУС: визначення пакета написане, але НЕ зібране в середовищі, де його
;; писали: у тому середовищі немає ні Guix, ні fpc. Твердження «збирається» тут
;; не робиться. Перевірка — робочий процес .github/workflows/fpc-install-cli.yml,
;; який виконує саме цю збірку, а потім порівнює коди виходу з Python CLI.
;;
;; Перед використанням вручну:
;;   guix build -L . -f wsm/packages/wsm-install-fpc.scm
;;
;; Пакет ставить один бінарник. Він не тягне Python, не тягне fcl-json (власний
;; розбір JSON у wsm_install_fpc/wsmjson.pas), не потребує root і не має жодного
;; шляху запису, крім stdout/stderr.

(define-module (wsm packages wsm-install-fpc)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (guix build-system trivial)
  #:use-module (gnu packages pascal)
  #:use-module (wsm licenses)
  #:export (wsm-install-fpc))

(define-public wsm-install-fpc
  (package
    (name "wsm-install-fpc")
    (version "0.1.0")
    ;; Only the Pascal tree is the source. The rest of the repository is not
    ;; an input to this binary, and including it would make the derivation
    ;; change whenever a document changed.
    (source (local-file "../../wsm_install_fpc" "wsm-install-fpc-source"
                        #:recursive? #t))
    (build-system trivial-build-system)
    (arguments
     (list
      #:builder
      #~(begin
          (use-modules (guix build utils))
          (let* ((out (assoc-ref %outputs "out"))
                 (bin (string-append out "/bin"))
                 (work (string-append (getcwd) "/pascal"))
                 (source (string-append #$source)))
            (mkdir-p bin)
            (mkdir-p work)
            (copy-recursively source work)
            ;; fpc writes unit files next to the sources and may look for a
            ;; per-user configuration; both are redirected into the build
            ;; directory so nothing escapes the sandbox.
            (setenv "HOME" work)
            ;; -Mobjfpc  the dialect both units declare
            ;; -Sh       ansistrings, which the JSON unit requires
            ;; -O2       the target is a 2 GB live medium
            ;; -Xs       strip symbols
            ;; -Fu/-FU   find and place unit files in the build directory
            ;; -FE       put the program in $out/bin
            ;; -o        name it after the front end, not the file
            (invoke #$(file-append fpc "/bin/fpc")
                    "-Mobjfpc" "-Sh" "-O2" "-Xs" "-vw"
                    (string-append "-Fu" work)
                    (string-append "-FU" work)
                    (string-append "-FE" bin)
                    "-owws-install-fpc"
                    (string-append work "/wsm_install_cli.pas"))
            (chmod (string-append bin "/wsm-install-fpc") #o555)
            ;; A wrapper is not installed on purpose: the binary must be the
            ;; thing the parity harness executes, with nothing in between.
            #t))))
    (native-inputs (list fpc))
    (synopsis "Read-only WSM installer front end, compiled")
    (description
     "Validates a WSM hardware report and reports whether the installer may
proceed, with the exit codes of the Python front end (0 accepted, 2 refused,
3 blocked on unresolved critical evidence).  The binary parses its own JSON,
selects the report schema version the document declares, and implements the
structural preflight rules that do not need a JSON Schema validator.  It does
not build the draft plan document, and the rules it does not implement are
listed in its source.  It never opens a block device, never spawns a process and
never requires root.")
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (license wsm-license)))
