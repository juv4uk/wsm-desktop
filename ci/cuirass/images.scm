;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; A Cuirass job module: the live image, built by Guix, on the pinned channels.
;;
;; Cuirass calls `cuirass-jobs' with the store and the specification arguments.
;; The image expression is the same one the release workflow builds, so this is
;; a second, independent path to the same derivation: if the workflow is green
;; and Cuirass is red, one of them is lying about the same bytes.
;;
;; This module lives under ci/ rather than wsm/ on purpose: wsm/ is the public
;; channel namespace, and every module there must be loadable by the channel's
;; evaluation test. A CI helper is not part of the channel's API.

(define-module (wsm ci images)
  #:use-module (guix store)
  #:use-module (guix derivations)
  #:use-module (gnu system image)
  #:use-module (gnu system)
  #:use-module (ice-9 match)
  #:export (cuirass-jobs))

(define (arguments->system arguments)
  "Return the system named in ARGUMENTS, defaulting to x86_64-linux."
  (match (assq-ref arguments 'system)
    (#f "x86_64-linux")
    (system system)))

(define* (image-jobs store systems #:key (profile "systems/live-minimal.scm"))
  "One job per system: build the live image expression."
  (map (lambda (system)
         (let* ((name (string->symbol
                       (string-append "wsm-live-minimal." system)))
                ;; The profile is read from the checked-out channel, so the job
                ;; always describes the source revision Cuirass just fetched.
                (os   (primitive-load profile))
                (drv  (operating-system-image
                       os
                       #:target system)))
           (derivation->job name drv)))
       systems))

(define (cuirass-jobs store arguments)
  "Register Cuirass jobs for the WSM live image."
  (define systems
    (list (arguments->system arguments)))
  ;; Grafting belongs on the user's machine, not in a build farm.
  (parameterize ((%graft? #f))
    (image-jobs store systems)))
