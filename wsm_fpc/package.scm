;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Guix package for the FPC slices of wsm-install.
;;
;; Build with:  guix build -f wsm_fpc/package.scm
;; Evaluate:    guix build -f wsm_fpc/package.scm --dry-run
;;
;; This file is deliberately standalone rather than a module under wsm/packages/:
;; that namespace is loadable by the Free-profile channel evaluation, and adding a
;; module there requires updating scripts/check_scheme_module_coverage.py and
;; tests/guix/source-module-evaluation.scm in the same change. Moving it there is
;; a separate step with its own tests, not a side effect of starting the port.
;;
;; Facts this record depends on, established from Guix and FPC documentation:
;;
;;   * fpc lives in (gnu packages pascal) and is in the official Guix channel;
;;   * fpc does NOT pull GTK or Lazarus - lazarus depends on fpc, not the reverse;
;;   * fpc shells out to gcc for linking, so gcc must be on PATH at build time;
;;   * fpc has no aarch64-linux support in Guix, so this package is x86_64 only;
;;   * FPC 3.2.2 ships no sha256 unit, hence the hand-written one in the source.

(use-modules (guix packages)
             (guix gexp)
             (guix build-system gnu)
             (gnu packages pascal)
             (gnu packages gcc)
             (srfi srfi-1)
             (srfi srfi-13)
             (wsm licenses))

(define-public wsm-plan-digest
  (package
    (name "wsm-plan-digest")
    (version "0.1.0")
    ;; Relative paths in local-file resolve against this file, so "../" is the
    ;; repository root. select? keeps .git and build output out of the store:
    ;; without it the source differs between clones and the build is not
    ;; reproducible.
    (source (local-file ".." "wsm-desktop-fpc-source"
                        #:recursive? #t
                        #:select? (lambda (path _stat)
                                    (not (any (lambda (skip)
                                                (string-contains path skip))
                                              '("/.git" "/__pycache__"))))))
    (build-system gnu-build-system)
    (arguments
     (list
      #:tests? #t
      ;; gnu-build-system passes these to make in the build, check and install
      ;; phases, so PREFIX reaches the install target that needs it.
      #:make-flags
      #~(list (string-append "FPC=" #$(file-append fpc "/bin/fpc"))
              (string-append "PREFIX=" #$output)
              "FPCFLAGS=-O2 -Sh -vw")
      #:phases
      #~(modify-phases %standard-phases
          ;; There is no ./configure in an FPC project.
          (delete 'configure)
          ;; The sources live in wsm_fpc/, and gnu-build-system starts at the root.
          (replace 'build
            (lambda* (#:key (make-flags '()) #:allow-other-keys)
              (with-directory-excursion "wsm_fpc"
                (apply invoke (cons "make" make-flags)))))
          (replace 'check
            (lambda* (#:key (make-flags '()) (tests? #t) #:allow-other-keys)
              (when tests?
                (with-directory-excursion "wsm_fpc"
                  (apply invoke (cons "make" (cons "check" make-flags)))))))
          (replace 'install
            (lambda* (#:key (make-flags '()) #:allow-other-keys)
              (with-directory-excursion "wsm_fpc"
                (apply invoke (cons "make" (cons "install" make-flags)))))))))
    ;; The compiler is a build-time tool and is not needed at run time, so it goes
    ;; in native-inputs. gcc is here because fpc calls it to link.
    (native-inputs (list fpc gcc))
    (supported-systems '("x86_64-linux"))
    (home-page "https://github.com/juv4uk/wsm-desktop")
    (synopsis "Canonical install-plan digest for WSM")
    (description
     "Computes the SHA-256 binding target that WSM consent records and journals
quote: a canonical JSON document over the target disk and its steps, serialized
with sorted keys, no whitespace and UTF-8 output.  Written in Free Pascal; the
program carries its own test vectors and fails when any digest differs from the
reference implementation.")
    (license wsm-license)))

wsm-plan-digest
