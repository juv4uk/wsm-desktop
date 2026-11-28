;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Source-tree Guix API/evaluation compatibility check against the exact
;; official Guix lock. This does not exercise WSM channel authentication.
;; WSM channel use by consumers requires the owner's signed Phase B bootstrap.
;;
;; Every module under wsm/ must be loaded here.
;; scripts/check_scheme_module_coverage.py enforces complete wsm/ coverage.
(use-modules (guix packages)
             (guix profiles)
             (guix store)
             (srfi srfi-1)
             (wsm systems performance)
             (wsm packages wsm)
             ((ci cuirass h170-free-packages) #:select (cuirass-jobs)))

(unless (and (list? %wsm-performance-services)
             (pair? %wsm-performance-services))
  (error "WSM performance module exported no service definitions"))

(unless (package? wsm-tools)
  (error "WSM package module did not export a package record for wsm-tools"))

;; Evaluate the standalone upstream-only H170 Free manifest against the lock.
(define h170-free-manifest
  (primitive-load "manifests/h170-free-upstream.scm"))
(unless (manifest? h170-free-manifest)
  (error "H170 Free package file did not produce a Guix manifest"))

(define h170-free-expected
  (list (cons "alsa-utils" "1.2.16")
        (cons "dosfstools" "4.2")
        (cons "e2fsprogs" "1.47.2")
        (cons "gptfdisk" "1.0.10")
        (cons "intel-vaapi-driver" "2.4.1")
        (cons "linux-libre" "7.3.5")
        (cons "mesa" "26.2.6")
        (cons "parted" "3.7")
        (cons "usbutils" "018")))

(define h170-free-entries (manifest-entries h170-free-manifest))
(define h170-free-actual
  (sort (map (lambda (entry)
               (cons (manifest-entry-name entry)
                     (manifest-entry-version entry)))
             h170-free-entries)
        (lambda (left right) (string<? (car left) (car right)))))
(unless (equal? h170-free-actual h170-free-expected)
  (error "H170 Free upstream package roots/versions differ from the pinned lock"
         h170-free-actual))

;; Exercise the real Cuirass package-job callback. It resolves package
;; derivations but does not build them or export NARs.
(with-store store
  (let* ((jobs (cuirass-jobs store '((systems . ("x86_64-linux")))))
         (actual
          (sort (map (lambda (job)
                       (let ((name (assoc-ref job #:package-name))
                             (version (assoc-ref job #:package-version))
                             (drv (assoc-ref job #:derivation)))
                         (unless (and (string? drv)
                                      (> (string-length drv) 0))
                           (error "Cuirass package job has no derivation" job))
                         (cons name version)))
                     jobs)
                (lambda (left right) (string<? (car left) (car right)))))
    (unless (equal? actual h170-free-expected)
      (error "Cuirass did not create one pinned package job per manifest root"
             actual))))

(display "WSM-SOURCE-MODULE-EVAL-OK ")
(display (length %wsm-performance-services))
(display " services, channel package: ")
(display (package-name wsm-tools))
(display " ")
(display (package-version wsm-tools))
(newline)
(display "H170-FREE-PACKAGE-MANIFEST-EVAL-OK: 9 official Guix package roots")
(newline)
(display "H170-FREE-CUIRASS-JOBS-EVAL-OK: 9 derivations resolved, not built")
(newline)