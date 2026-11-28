;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass custom job module for the WSM minimal live image.
;; Module name matches this path: ci/cuirass/images.scm -> (ci cuirass images).
;;
;; The pinned Guix API exports image->job and arguments->systems from (gnu ci),
;; and image-with-os / iso9660-image from (gnu system image).

(define-module (ci cuirass images)
  #:use-module (gnu ci)
  #:use-module (gnu system image)
  #:use-module (ice-9 ftw)
  #:export (cuirass-jobs))

(define (load-live-minimal)
  "Load the live-minimal operating-system from the checked-out WSM channel."
  (let ((profile (search-path %load-path "systems/live-minimal.scm")))
    (unless profile
      (error "Cuirass could not find systems/live-minimal.scm in the WSM channel"))
    (primitive-load profile)))

(define (cuirass-jobs store arguments)
  "Return one Cuirass image job for each requested system."
  (let* ((systems (arguments->systems arguments))
         (os (load-live-minimal))
         (image (image-with-os iso9660-image os)))
    (map (lambda (system)
           (image->job store image
                       #:name "wsm-live-minimal"
                       #:system system))
         systems)))
