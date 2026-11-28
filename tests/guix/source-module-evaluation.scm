;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Source-tree Guix API/evaluation compatibility check against the exact
;; official Guix lock. This does not exercise WSM channel lookup/authentication.
;; WSM channel authentication requires the owner's signed Phase B bootstrap.
;;
;; Every module under wsm/ must be loaded here.
;; scripts/check_scheme_module_coverage.py enforces complete wsm/ coverage.
(use-modules (guix packages)
             (guix profiles)
             (guix store)
             (gnu services)
             (srfi srfi-1)
             (wsm systems performance)
             (wsm packages wsm)
             ((ci cuirass h170-free-packages) #:select (cuirass-jobs)))

(unless (and (list? %wsm-performance-services)
             (pair? %wsm-performance-services))
  (error "WSM performance module exported no service definitions"))

(unless (package? wsm-tools)
  (error "WSM package module did not export a package record for wsm-tools"))

;; Resolve the exact package roots from the upstream-only H170 Free manifest.
(define h170-free-manifest
  (primitive-load "drivers/profiles/h170-free-packages.scm"))
(unless (manifest? h170-free-manifest)
  (error "H170 Free package source did not evaluate to a Guix manifest"))

(define h170-free-expected
  '("linux-libre" "mesa" "vulkan-loader" "vulkan-tools"
    "pciutils" "usbutils" "alsa-utils" "ethtool"
    "nvme-cli" "smartmontools" "lm-sensors"))
(define h170-free-entries (manifest-entries h170-free-manifest))
(define h170-free-actual
  (sort (map manifest-entry-name h170-free-entries) string<?))
(unless (equal? h170-free-actual (sort h170-free-expected string<?))
  (error "H170 Free manifest roots differ from the reviewed package set"
         h170-free-actual))

;; Exercise the real Cuirass callback. This lowers package definitions to
;; derivation metadata; it does not build the outputs or export NARs.
(with-store store
  (let* ((jobs (cuirass-jobs store '((systems . ("x86_64-linux")))))
         (job-names (map (lambda (job)
                           (let ((name (assoc-ref job #:package-name))
                                 (version (assoc-ref job #:package-version))
                                 (drv (assoc-ref job #:derivation)))
                             (unless (and (string? name)
                                          (string? version)
                                          (> (string-length version) 0)
                                          (string? drv)
                                          (> (string-length drv) 0))
                               (error "Cuirass package job lacks derivation metadata" job))
                             name))
                         jobs)))
    (unless (equal? (sort job-names string<?)
                    (sort h170-free-expected string<?))
      (error "Cuirass H170 job set does not match the manifest roots" job-names))
    (display "H170-FREE-CUIRASS-JOBS-EVAL-OK: ")
    (display (length jobs))
    (display " package derivations resolved, not built")
    (newline)))

;; Evaluate the actual Cuirass host service declaration. This creates a
;; Guix service object but neither registers nor starts the Cuirass instance.
(primitive-load "ci/cuirass/service.scm")
(unless (service? wsm-cuirass-service)
  (error "Cuirass host fragment did not create a Guix service object"))

(display "WSM-SOURCE-MODULE-EVAL-OK ")
(display (length %wsm-performance-services))
(display " services, channel package: ")
(display (package-name wsm-tools))
(display " ")
(display (package-version wsm-tools))
(newline)
(display "H170-FREE-PACKAGE-MANIFEST-EVAL-OK: 11 official Guix roots")
(newline)
(display "WSM-CUIRASS-SERVICE-EVAL-OK: service object created, instance NOT_RUN")
(newline)