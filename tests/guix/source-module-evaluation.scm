;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Source-tree Guix API/evaluation check for the exact official channel lock.
(use-modules (guix packages)
             (guix licenses)
             (wsm systems performance)
             (wsm packages wsm)
             (wsm packages linux-libre))

(unless (and (list? %wsm-performance-services)
             (pair? %wsm-performance-services))
  (error "WSM performance module exported no service definitions"))

(unless (package? wsm-tools)
  (error "WSM package module did not export wsm-tools"))

(unless (and (package? linux-libre-h170)
             (string=? (package-name linux-libre-h170) "linux-libre-h170"))
  (error "H170 Linux-libre package module did not export linux-libre-h170"))

(let ((license (package-license wsm-tools)))
  (unless (and (license? license)
               (string=? (license-name license) "ВОЛЬНІСТЬ")
               (string=? (license-uri license) "file://LICENSE"))
    (error "wsm-tools license metadata does not match LicenseRef-Volnist")))

(display "WSM-SOURCE-MODULE-EVAL-OK ")
(display (length %wsm-performance-services))
(display " services, channel package: ")
(display (package-name wsm-tools))
(display " ")
(display (package-version wsm-tools))
(newline)
