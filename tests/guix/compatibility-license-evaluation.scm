;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Evaluate the Compatibility live profile under its own pinned Guix + Nonguix
;; lock and assert that its WSM-owned package retains the owner's license.

(use-modules (guix licenses)
             (guix packages)
             (wsm licenses))

(primitive-load "systems/live-compat.scm")

(unless (and (package? wsm-live-tools)
             (eq? (package-license wsm-live-tools) wsm-license)
             (string=? (license-name (package-license wsm-live-tools))
                       "ВОЛЬНІСТЬ")
             (string=? (license-uri (package-license wsm-live-tools))
                       "file://LICENSE"))
  (error "Compatibility live package does not preserve LicenseRef-Volnist"))

(display "WSM-COMPATIBILITY-LICENSE-EVAL-OK ")
(display (license-name (package-license wsm-live-tools)))
(newline)
