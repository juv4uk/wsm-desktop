;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; The Guix metadata object names the owner's actual project license and points
;; at its complete text inside each WSM package source tree.  It deliberately
;; does not classify ВОЛЬНІСТЬ as GPL, non-copyleft, OSI-approved, or FSDG-free.

(define-module (wsm licenses)
  #:use-module (guix licenses)
  #:export (wsm-license))

;; `license' is the <license> record constructor, but Guix does not export it
;; from (guix licenses).  `(@ (guix licenses) license) reaches that binding
;; explicitly, so the owner's actual license metadata survives instead of
;; being replaced by a misleading `non-copyleft' or GPL category.  Guix 1.5.0
;; evaluates this successfully; a future Guix that removes the binding must be
;; handled by a reviewed migration, not by silently changing the license.
(define wsm-license
  ((@ (guix licenses) license)
   "ВОЛЬНІСТЬ"
   "file://LICENSE"
   "LicenseRef-Volnist; власна ліцензія WSM Desktop."))
