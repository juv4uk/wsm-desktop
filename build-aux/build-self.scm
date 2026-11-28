;;; SPDX-License-Identifier: LicenseRef-Volnist
;;;
;;; Self-build script for the WSM Desktop Guix channel.
;;;
;;; Guix's default channel builder compiles every '.scm' file under the
;;; channel root and expects each one to declare the module implied by its
;;; path.  This repository intentionally keeps machine configurations,
;;; channel locks and Cuirass specs as plain '.scm' data at the root, so the
;;; default builder fails on, for example, (channels lock).  Setting
;;; (directory "wsm") in .guix-channel would avoid those files but would also
;;; strip the 'wsm' prefix from every module name, breaking the public
;;; (wsm packages wsm) API that source-tree consumers already use with -L .
;;;
;;; This script keeps the repository root as the Guile module root and makes
;;; the channel available from source: the checkout is symlinked into
;;; 'share/guile/site/<version>' and no '.go' files are produced.  Guile
;;; happily loads '.scm' directly, so the channel works without compiling
;;; Guix's own modules into the build sandbox (which requires the complete
;;; pinned Guix environment and fails when done from a bare gexp).
;;;
;;; Compilation can be added later via a proper inferior-based self-build
;;; once channel authentication is bootstrapped.  Source-only loading is a
;;; supported Guix channel form and preserves the exact namespace and
;;; relative local-file paths used by the package recipes.

(define-module (build-self)
  #:use-module (guix)
  #:export (build))

(define* (build source
                #:key
                verbose?
                version
                channel-metadata
                system
                (pull-version 1)
                built-in-builders
                #:allow-other-keys
                #:rest rest)
  "Return a source-only derivation for WSM modules in SOURCE.  The repository
root stays the module root, so (wsm ...) keeps its namespace and relative
local-file paths keep pointing at the checkout root."
  (if (< pull-version 1)
      #f
      (gexp->derivation
       "wsm"
       #~(begin
           (use-modules (guix build utils))

           (define scm
             (string-append #$output "/share/guile/site/"
                            (effective-version)))
           (mkdir-p (dirname scm))
           (symlink #$source scm)))))

;; 'guix pull' takes the last expression of this file as the build procedure.
build
