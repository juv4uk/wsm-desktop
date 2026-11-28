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
(use-modules (guix licenses)
             (guix packages)
             (gnu packages linux)
             (wsm licenses)
             (wsm systems performance)
             (wsm packages wsm)
             (wsm packages linux-libre)
             (wsm packages fpc-tools))

(unless (and (list? %wsm-performance-services)
             (pair? %wsm-performance-services))
  (error "WSM performance module exported no service definitions"))

;; The channel's own package module: until it is loaded here it was never
;; evaluated, and its header said so ("не зібрано й не перевірено").
(unless (package? wsm-tools)
  (error "WSM package module did not export a package record for wsm-tools"))

;; Check the exact owner-supplied license metadata, without substituting a category.
(unless (and (license? wsm-license)
             (string=? (license-name wsm-license) "ВОЛЬНІСТЬ")
             (string=? (license-uri wsm-license) "file://LICENSE")
             (string=? (license-comment wsm-license)
                       "LicenseRef-Volnist; власна ліцензія WSM Desktop.")
             (eq? (package-license wsm-tools) wsm-license))
  (error "WSM Guix license metadata does not preserve LicenseRef-Volnist"))

;; Native Pascal packages must keep the actual owner license and the compiler
;; only in native-inputs. No Python interpreter is part of any runtime.
(unless (and (package? wsm-hwcheck-fpc)
             (package? wsm-classify-fpc)
             (package? wsm-partition-fpc)
             (string=? (package-name wsm-hwcheck-fpc) "wsm-hwcheck-fpc")
             (string=? (package-name wsm-classify-fpc) "wsm-classify-fpc")
             (string=? (package-name wsm-partition-fpc) "wsm-partition-fpc")
             (eq? (package-license wsm-hwcheck-fpc) wsm-license)
             (eq? (package-license wsm-classify-fpc) wsm-license)
             (eq? (package-license wsm-partition-fpc) wsm-license)
             (pair? (package-native-inputs wsm-hwcheck-fpc))
             (pair? (package-native-inputs wsm-classify-fpc))
             (pair? (package-native-inputs wsm-partition-fpc)))
  (error "FPC packages must use LicenseRef-Volnist and a build-time compiler only"))

;; Force Guix to evaluate all actual package sources, not just module names.
(unless (and (package-source wsm-hwcheck-fpc)
             (package-source wsm-classify-fpc)
             (package-source wsm-partition-fpc))
  (error "FPC package sources did not evaluate"))

;; Evaluate the ordinary live profile as well as the standalone channel module.
(primitive-load "systems/live-iso.scm")
(unless (and (package? wsm-live-tools)
             (eq? (package-license wsm-live-tools) wsm-license))
  (error "Live ISO package does not preserve LicenseRef-Volnist"))

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
(display " services, channel package: ")
(display (package-name wsm-tools))
(display " ")
(display (package-version wsm-tools))
(newline)
