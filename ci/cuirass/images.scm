;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; A Cuirass job module for the WSM Minimal Live ISO.
;;
;; The module name matches this file's path from the WSM channel root.
;; Cuirass calls cuirass-jobs with the store and specification arguments.

(define-module (ci cuirass images)
  #:use-module (gnu ci)
  #:use-module (gnu image)
  #:use-module (gnu system image)
  #:use-module (ice-9 ftw)
  #:use-module (ice-9 match)
  #:export (cuirass-jobs))

(define (arguments->system arguments)
  "Return the system named in ARGUMENTS, defaulting to x86_64-linux."
  (match (assq-ref arguments 'system)
    (#f "x86_64-linux")
    (system system)))

(define (channel-file relative-path)
  "Resolve RELATIVE-PATH from the checked-out channel in %load-path."
  (or (search-path %load-path relative-path)
      (error "cannot find WSM channel file in Guile load path" relative-path)))

(define* (image-jobs store systems #:key (profile "systems/live-minimal.scm"))
  "Return Cuirass jobs for the WSM Minimal Live ISO."
  (map (lambda (system)
         (let ((os (primitive-load (channel-file profile))))
           ;; image->job is the pinned Guix API. It lowers the image record
           ;; through system-image, then returns the derivation as a Cuirass job.
           (image->job store
                       (image (inherit iso9660-image)
                              (operating-system os))
                       #:name "wsm-live-minimal"
                       #:system system)))
       systems))

(define (cuirass-jobs store arguments)
  "Register Cuirass jobs for the WSM Minimal Live ISO."
  (image-jobs store (list (arguments->system arguments))))
