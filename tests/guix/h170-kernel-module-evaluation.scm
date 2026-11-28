;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Evaluate only the H170 kernel candidate and its pinned official upstream base.
;; This deliberately does not import any WSM-owned application/tool package.

(use-modules (guix packages)
             (gnu packages linux)
             (wsm packages linux-libre))

(define base-package linux-libre)
(define h170-package linux-libre-h170)
(define base-source (package-source base-package))
(define h170-source (package-source h170-package))
(define base-patches (origin-patches base-source))
(define h170-patches (origin-patches h170-source))

(unless (and (package? h170-package)
             (string=? (package-name h170-package) "linux-libre-h170")
             (string=? (package-version h170-package)
                       (package-version base-package))
             (equal? (package-license h170-package)
                     (package-license base-package)))
  (error "H170 kernel candidate does not preserve pinned upstream package identity"))

(unless (= (length h170-patches) (+ (length base-patches) 1))
  (error "H170 kernel candidate must append exactly one upstream patch"))

(format #t "H170 kernel module evaluated: ~a ~a; patches: ~a -> ~a~%"
        (package-name h170-package)
        (package-version h170-package)
        (length base-patches)
        (length h170-patches))
