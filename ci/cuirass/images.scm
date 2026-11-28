;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass custom job for the WSM minimal live ISO.
;;
;; This module name matches the channel-relative path:
;; ci/cuirass/images.scm -> (ci cuirass images).
;; Keep the helper outside the public (wsm ...) channel namespace.
;;
;; Use the API exported by the exact Guix revision in channels.lock.scm.
;; image->job performs the store-monad lowering and derivation->job conversion.

(define-module (ci cuirass images)
  #:use-module ((gnu ci) #:select (arguments->systems image->job))
  #:use-module ((gnu system image) #:select (image-with-os iso9660-image))
  #:use-module (ice-9 ftw)
  #:export (cuirass-jobs))

(define %wsm-image-system "x86_64-linux")

(define (load-live-minimal)
  "Load the live-minimal operating-system from the checked-out WSM channel."
  (let ((profile (search-path %load-path "systems/live-minimal.scm")))
    (unless profile
      (error "Cuirass could not find systems/live-minimal.scm in the WSM channel"))
    (primitive-load profile)))

(define (cuirass-jobs store arguments)
  "Return a Cuirass image job for the WSM release system."
  (let* ((systems (filter (lambda (system)
                            (string=? system %wsm-image-system))
                          (arguments->systems arguments)))
         (os (load-live-minimal))
         (image (image-with-os iso9660-image os)))
    (unless (pair? systems)
      (error "Cuirass request does not include the WSM image system"
             %wsm-image-system))
    (map (lambda (system)
           (image->job store image
                       #:name "wsm-live-minimal-image"
                       #:system system))
         systems)))
