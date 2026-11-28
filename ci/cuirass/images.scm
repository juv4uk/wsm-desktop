;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass custom job for the WSM minimal live ISO.
;;
;; Cuirass supplies a plural 'systems' argument. Reuse Guix's own
;; arguments->systems and image->job helpers so this job follows the pinned
;; Guix CI API and produces the same ISO9660 image type as the release workflow.

(define-module (ci cuirass images)
  #:use-module (gnu ci)
  #:use-module (gnu system image)
  #:use-module (guix packages)
  #:export (cuirass-jobs))

(define* (image-jobs store systems #:key (profile "systems/live-minimal.scm"))
  "Build one ISO9660 image job for each requested system."
  ;; Resolve the profile from the WSM channel revision Cuirass fetched.
  (let ((image (image-with-os iso9660-image (primitive-load profile))))
    (map (lambda (system)
           (image->job store image
                       #:name "wsm-live-minimal"
                       #:system system))
         systems)))

(define (cuirass-jobs store arguments)
  "Register the WSM live ISO jobs requested by Cuirass."
  ;; These are the same no-graft semantics used by Guix's built-in image jobs.
  (parameterize ((%graft? #f))
    (image-jobs store (arguments->systems arguments))))
