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
;;; This script keeps the repository root as the Guile module root and only
;;; compiles the real public modules under 'wsm/'.  Because gexp->derivation
;;; runs in a bare Guile that does not ship Guix's own modules, we import the
;;; source-module closure of everything the WSM modules use, the same way
;;; Guix's own build-aux/build-self.scm does.

(define-module (build-self)
  #:use-module (guix)
  #:use-module (guix modules)
  #:export (build))

(define %wsm-module-dependencies
  ;; Top-level modules imported by wsm/**/*.scm, plus the builder helpers.
  '((guix build compile)
    (guix build utils)
    (guix packages)
    (guix gexp)
    (guix licenses)
    (guix utils)
    (guix download)
    (guix git-download)
    (guix build-system python)
    (gnu packages linux)
    (gnu packages python)
    (gnu packages python-build)
    (gnu packages python-xyz)
    (gnu services)
    (gnu services linux)))

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
  "Return a derivation compiling only WSM modules from SOURCE.  The repository
root stays the module root, so (wsm ...) keeps its namespace and relative
local-file paths keep pointing at the checkout root."
  (if (< pull-version 1)
      #f
      (with-imported-modules
       (source-module-closure %wsm-module-dependencies)
       (gexp->derivation
        "wsm"
        #~(begin
            (use-modules (guix build compile)
                         (guix build utils))

            (define go
              (string-append #$output "/lib/guile/" (effective-version)
                             "/site-ccache"))
            (define scm
              (string-append #$output "/share/guile/site/"
                             (effective-version)))

            (mkdir-p go)
            (compile-files #$source go
                           (find-files (string-append #$source "/wsm")
                                       "\\.scm$"))
            (mkdir-p (dirname scm))
            (symlink #$source scm))))))

;; 'guix pull' takes the last expression of this file as the build procedure.
build
