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
                ;; A relative local-file resolves against this module's directory, so the
                ;; patch is found from a checkout or an authenticated channel checkout.
                (list (local-file "patches/linux-libre-h170-nouveau-atomic.patch"
                                  "linux-libre-h170-nouveau-atomic.patch"))))))
    ;; Without these two fields `guix show linux-libre-h170` reports the upstream
    ;; synopsis and description, so a reader cannot tell that this is a patched
    ;; candidate — or what it does not fix.
    (synopsis "Linux-libre kernel with the upstream Nouveau atomic-KMS fix (H170 candidate)")
    (description
     "The pinned Guix @code{linux-libre} package with the upstream mainline patch
that restores @code{drm_mode_config_funcs.atomic_check} and @code{atomic_commit} for
Nouveau, taken from commit @code{ed7fb901fce3}.  It inherits upstream source,
deblobbing, configuration and inputs unchanged and adds no firmware and no
proprietary module.

This is a build candidate for the WSM H170 reference machine.  It does not provide
GP107 FECS/GPCCS firmware, so GR 3D and compute remain unavailable, and it is not a
statement that the kernel boots, binds or renders on that board.")))
