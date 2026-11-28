;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; The Guix metadata object names the owner's actual project license and points
;; at its complete text inside each WSM package source tree.  It deliberately
;; does not classify ВОЛЬНІСТЬ as GPL, non-copyleft, OSI-approved, or FSDG-free.

(define-module (wsm licenses)
  #:use-module (guix licenses)
  #:export (wsm-license))

(define wsm-license
  (license "ВОЛЬНІСТЬ"
           "file://LICENSE"
           "LicenseRef-Volnist; власна ліцензія WSM Desktop."))
