;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Source-tree Guix API/evaluation compatibility check against the exact
;; official Guix lock. This does not exercise WSM channel lookup/authentication.
;; The latter requires the owner's signed introduction and a dedicated lock.
;;
;; Every module under wsm/ must be loaded here: this file is the only place
;; where source modules are evaluated by Guix for real, so a module missing
;; from this list is a module nobody has checked.
;; scripts/check_scheme_module_coverage.py enforces that rule.
(use-modules (guix packages)
             (guix licenses)
             (gnu packages linux)
             (wsm systems performance)
             (wsm packages wsm)
             (wsm packages linux-libre))

(unless (and (list? %wsm-performance-services)
             (pair? %wsm-performance-services))
  (error "WSM performance module exported no service definitions"))

;; WSM-owned package: the effective package metadata must match the repository
;; license text. This does not assert OSI/FSDG approval or upstream Guix acceptance.
(unless (package? wsm-tools)
  (error "WSM package module did not export a package record for wsm-tools"))

(let ((license (package-license wsm-tools)))
  (unless (and (license? license)
               (string=? (license-name license) "ВОЛЬНІСТЬ")
               (string=? (license-uri license) "file://LICENSE"))
    (error "wsm-tools license metadata does not match LicenseRef-Volnist")))

;; H170 Free overlay: preserve upstream kernel metadata and append exactly one patch.
(unless (and (package? linux-libre-h170)
             (string=? (package-name linux-libre-h170) "linux-libre-h170")
             (string=? (package-version linux-libre-h170)
                       (package-version linux-libre))
             (equal? (package-license linux-libre-h170)
                     (package-license linux-libre)))
  (error "H170 kernel overlay diverges from the pinned linux-libre package"))

(let ((base-patches (origin-patches (package-source linux-libre)))
      (h170-patches (origin-patches (package-source linux-libre-h170))))
  (unless (= (length h170-patches) (+ (length base-patches) 1))
    (error "H170 kernel overlay must append exactly one patch to linux-libre")))

(display "WSM-SOURCE-MODULE-EVAL-OK ")
(display (length %wsm-performance-services))
(display " services, WSM package: ")
(display (package-name wsm-tools))
(display " ")
(display (package-version wsm-tools))
(display "; H170 kernel: ")
(display (package-name linux-libre-h170))
(display " ")
(display (package-version linux-libre-h170))
(newline)
