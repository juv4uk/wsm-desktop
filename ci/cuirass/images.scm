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
  #:use-module (ice-9 ftw)
  #:export (cuirass-jobs))

(define* (load-channel-profile profile)
  "Load PROFILE from the WSM channel checkout on the Guile load path.
Do not resolve it against the Cuirass worker's process working directory."
  (let ((file (search-path %load-path profile)))
    (unless file
      (error "WSM channel profile is absent from Guile load path: ~a" profile))
    (primitive-load file)))

(define* (image-jobs store systems #:key (profile "systems/live-minimal.scm"))
  "Build one ISO9660 image job for each requested system."
  (let ((image (image-with-os iso9660-image (load-channel-profile profile))))
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
