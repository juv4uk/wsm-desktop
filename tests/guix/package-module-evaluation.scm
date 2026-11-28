;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Load every module under wsm/packages/ and touch what it exports.
;;
;; Why this exists: nothing in CI ever loaded these modules. A package definition that
;; does not compile, an unbound variable, a licence record that does not resolve — all
;; of it passed every check this repository had, because the only thing that read the
;; files was Python looking for strings. `guix system build` loads systems/*.scm, and
;; those import these modules only sometimes.
;;
;; The list below must name every module in wsm/packages/. A Python test
;; (tests/test_guix_package_modules.py) fails when a module is added and not listed
;; here, so a new package cannot be born unevaluated.

(use-modules (ice-9 match)
             (srfi srfi-1)
             (guix packages)
             (guix licenses))

;; Keep this list in step with `ls wsm/packages/*.scm`.
(use-modules (wsm packages wsm))
(use-modules (wsm packages linux-libre))

(define failures 0)

(define (report label thunk)
  "Run THUNK, and record a failure rather than aborting the whole evaluation."
  (catch #t
    (lambda ()
      (let ((value (thunk)))
        (format #t "OK   ~a: ~a~%" label
                (cond ((package? value) (package-name value))
                      ((string? value) value)
                      (else value)))))
    (lambda (key . args)
      (set! failures (+ failures 1))
      (format (current-error-port) "FAIL ~a: ~a ~s~%" label key args))))

;; Loading the module is half of it; touching each package forces the fields to
;; resolve, which is where an unbound variable or a bad licence record shows up.
(report "wsm-tools" (lambda ()
                      (let ((p wsm-tools))
                        (package-license p)
                        (package-source p)
                        p)))

(report "linux-libre-h170" (lambda ()
                             (let ((p linux-libre-h170))
                               (package-license p)
                               (package-source p)
                               p)))

(if (zero? failures)
    (format #t "~%all package modules evaluated~%")
    (begin
      (format (current-error-port) "~%~a package module(s) failed to evaluate~%" failures)
      (exit 1)))
