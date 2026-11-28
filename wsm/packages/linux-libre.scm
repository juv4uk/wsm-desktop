;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; H170 Free candidate: linux-libre with the upstream GP107 Nouveau atomic-KMS fix.
;;
;; This inherits the exact pinned Guix linux-libre package (source, deblob
;; transformations, configuration, build phases, inputs, supported systems,
;; kernel ABI and license) and appends one upstream Linux patch. It does not
;; add NVIDIA firmware, Nonguix, proprietary modules, or a second kernel recipe.
;;
;; The patch fixes Nouveau atomic modesetting initialization. It does not
;; provide GP107 FECS/GPCCS firmware, GR 3D/compute, reclocking, or physical
;; H170 acceptance. The package remains a build candidate until Guix evaluation,
;; build/closure and separately approved H170 runtime checks are complete.

(define-module (wsm packages linux-libre)
  #:use-module (guix packages)
  #:use-module (guix gexp)
  #:use-module (gnu packages linux)
  #:use-module (ice-9 ftw)
  #:export (linux-libre-h170))

(define %h170-nouveau-atomic-patch
  (or (search-path %load-path
                   "wsm/packages/patches/linux-libre-h170-nouveau-atomic.patch")
      (error "H170 Nouveau atomic patch is missing from the WSM channel")))

(define-public linux-libre-h170
  (package
    (inherit linux-libre)
    (name "linux-libre-h170")
    (source
     (origin
       (inherit (package-source linux-libre))
       (patches
        (append (origin-patches (package-source linux-libre))
                (list (local-file %h170-nouveau-atomic-patch
                                  "linux-libre-h170-nouveau-atomic.patch"))))))))
