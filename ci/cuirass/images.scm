;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; A Cuirass job module: the live ISO, built by Guix on the pinned channels.
;;
;; Cuirass calls `cuirass-jobs' with the store and the specification arguments.
;; Reuse Guix's own image->job helper so image derivation construction follows
;; the same supported path as upstream Guix CI. The release uses
;; --image-type=iso9660, represented here by iso9660-image.
;;
;; This module lives under ci/ rather than wsm/ on purpose: wsm/ is the public
;; channel namespace, and every module there must be loadable by the channel's
;; evaluation test. A CI helper is not part of the channel's API. Because of that,
;; its module name must match this path — a channel with no `directory` resolves
;; (wsm X) to <checkout>/wsm/X.scm, so a `(wsm ci images)` name here would look for
;; wsm/ci/images.scm and find nothing.

(define-module (ci cuirass images)
  #:use-module (guix store)
  #:use-module (guix packages)
  #:use-module (gnu ci)
  #:use-module (gnu image)
  #:use-module (gnu system image)
  #:use-module (gnu system)
  #:use-module (ice-9 match)
  #:use-module (srfi srfi-1)
  #:export (cuirass-jobs))

(define (arguments->system arguments)
  "Return the system named in ARGUMENTS, defaulting to x86_64-linux."
  (match (assq-ref arguments 'system)
    (#f "x86_64-linux")
    (system system)))

(define* (image-jobs store systems #:key (profile "systems/live-minimal.scm"))
  "One job per system: build the live ISO with Guix's supported image helper."
  ;; Load once from the checked-out WSM channel revision Cuirass evaluated.
  (let ((os (primitive-load profile)))
    (map (lambda (system)
           (image->job store
                       (image (inherit iso9660-image)
                              (operating-system os))
                       #:name "wsm-live-minimal"
                       #:system system))
         systems)))

(define (cuirass-jobs store arguments)
  "Register Cuirass jobs for the WSM live image."
  (define systems
    (list (arguments->system arguments)))
  ;; Grafting belongs on the user's machine, not in a build farm.
  (parameterize ((%graft? #f))
    (image-jobs store systems)))
