;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Source-tree Guix API/evaluation compatibility check against the exact
;; official Guix lock. This does not exercise WSM channel lookup/authentication.
;; The latter requires the owner's signed introduction and a dedicated lock.
(use-modules (guix packages)
             (guix licenses)
             (gnu packages linux)
             (wsm systems performance)
             (wsm packages wsm)
             (wsm packages linux-libre))

(unless (and (list? %wsm-performance-services)
             (pair? %wsm-performance-services))
  (error "WSM performance module exported no service definitions"))

(unless (and (package? wsm-tools)
             (string=? (package-version wsm-tools) "0.1.0-rc7"))
  (error "WSM package module did not export wsm-tools 0.1.0-rc7"))

(let ((lic (package-license wsm-tools)))
  (unless (and (license? lic)
               (string=? (license-name lic) "ВОЛЬНІСТЬ")
               (string=? (license-uri lic) "file://LICENSE"))
    (error "wsm-tools license metadata does not match LicenseRef-Volnist")))

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
