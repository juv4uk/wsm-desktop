;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; A Cuirass job module: the live image, built by Guix, on the pinned channels.
;;
;; Cuirass resolves this module through the channel root, so the namespace must
;; match the file path: `ci/cuirass/images.scm' is `(ci cuirass images)'.
;; An earlier revision named it `(wsm ci images)' and pointed the spec at that
;; name - Cuirass would have failed to resolve it, because `wsm/' holds only
;; packages and systems.
;;
;; `system-image' is the procedure that turns an <image> record into a
;; derivation. It takes the image, not the operating system, has no #:target
;; keyword, and is monadic - so the store plumbing below is required, not
;; decorative.

(define-module (ci cuirass images)
  #:use-module (guix store)
  #:use-module (guix monads)
  #:use-module (guix derivations)
  #:use-module (gnu ci)
  #:use-module (gnu system image)
  #:use-module (gnu system)
  #:use-module (ice-9 match)
  #:export (cuirass-jobs))

(define (arguments->systems arguments)
  "Return the list of systems named in ARGUMENTS.

Cuirass passes `((channels . ...) (systems . (...)) (subset . ...))'. The key is
`systems' and its value is a list; an earlier revision read `system' and
silently ignored the specification's systems."
  (match (assq-ref arguments 'systems)
    (#f (list (%current-system)))
    ((? list? systems) systems)
    (system (list system))))

(define (profile-image profile)
  "Build the <image> record for PROFILE, reading the profile from the channel."
  (image-with-os efi-disk-image (primitive-load profile)))

(define* (image-jobs store systems #:key (profile "systems/live-minimal.scm"))
  "One job per system: the live image, lowered in that system."
  (map (lambda (system)
         (let* ((name (string->symbol
                       (string-append "wsm-live-minimal." system)))
                (image (profile-image profile))
                (drv (run-with-store store
                       (mbegin %store-monad
                         (set-guile-for-build (default-guile))
                         (lower-object (system-image image) system)))))
           (derivation->job name drv)))
       systems))

(define (cuirass-jobs store arguments)
  "Register Cuirass jobs for the WSM live image."
  ;; Grafting is meant to happen on the user's machine; Guix's own image job
  ;; does the same.
  (parameterize ((%graft? #f))
    (image-jobs store (arguments->systems arguments))))
