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
  #:export (linux-libre-h170))

(define-public linux-libre-h170
  (package
    (inherit linux-libre)
    (name "linux-libre-h170")
    (source
     (origin
       (inherit (package-source linux-libre))
       (patches
        (append (origin-patches (package-source linux-libre))
                ;; A relative local-file resolves against the directory of *this*
                ;; file, so the patch is found whether the module is loaded from the
                ;; checkout, from a channel, or from the store. The previous version
                ;; searched %load-path for a repository-relative path, which only
                ;; works while "." happens to be on the load path.
                (list (local-file "patches/linux-libre-h170-nouveau-atomic.patch"
                                  "linux-libre-h170-nouveau-atomic.patch"))))))))
