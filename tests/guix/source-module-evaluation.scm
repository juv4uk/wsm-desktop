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
(use-modules (srfi srfi-1)
             (guix licenses)
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

;; Evaluate all native FPC packages and preserve their runtime dependency boundary.
(define fpc-packages
  (list wsm-hwcheck-fpc wsm-classify-fpc wsm-partition-fpc
        wsm-profile-fpc wsm-preflight-fpc wsm-install-fpc))
(unless (equal? (map package-name fpc-packages)
                '("wsm-hwcheck-fpc" "wsm-classify-fpc" "wsm-partition-fpc"
                  "wsm-profile-fpc" "wsm-preflight-fpc" "wsm-install-fpc"))
  (error "FPC package definitions are incomplete or out of order"))
(unless (every (lambda (package)
                 (eq? (package-license package) wsm-license))
               fpc-packages)
  (error "FPC packages must preserve LicenseRef-Volnist"))
(unless (= (length (package-inputs wsm-install-fpc)) 5)
  (error "FPC installer must have five explicit runtime reader inputs"))
(unless (= (length (package-native-inputs wsm-install-fpc)) 1)
  (error "FPC compiler must remain a build-time input only"))

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
