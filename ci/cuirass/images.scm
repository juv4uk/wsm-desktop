;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass custom job for the WSM minimal live ISO.
;;
;; The module name follows this file's channel-relative path:
;; ci/cuirass/images.scm -> (ci cuirass images).
;; Keep this helper outside the public (wsm ...) channel namespace.
;;
;; Use the public Cuirass API from the exact Guix revision in channels.lock.scm.
;; Do not duplicate the lower-object / store-monad work performed by image->job.

(define-module (ci cuirass images)
  #:use-module ((gnu ci) #:select (arguments->systems image->job))
  #:use-module ((gnu system image) #:select (image-with-os iso9660-image))
  #:use-module (ice-9 ftw)
  #:export (cuirass-jobs))

(define %wsm-image-system "x86_64-linux")

(define (live-minimal-operating-system)
  "Load the live profile from the WSM channel checkout on the Guile load path."
  (let ((profile (search-path %load-path "systems/live-minimal.scm")))
    (unless profile
      (error "cannot find WSM live profile in the channel load path"
             "systems/live-minimal.scm"))
    (primitive-load profile)))

(define (cuirass-jobs store arguments)
  "Register the WSM minimal live ISO job for supported requested systems."
  ;; The image is deliberately built only for the project's release target.
  ;; arguments->systems is Cuirass's own parser for its systems argument.
  (let ((systems (filter (lambda (system)
                           (string=? system %wsm-image-system))
                         (arguments->systems arguments)))
        (image (image-with-os iso9660-image
                              (live-minimal-operating-system))))
    (unless (pair? systems)
      (error "Cuirass request does not include the WSM image system"
             %wsm-image-system))
    (map (lambda (system)
           (image->job store image
                       #:name "wsm-live-minimal-image"
                       #:system system))
         systems)))
