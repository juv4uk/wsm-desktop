;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM development channel set.
;;
;; Keep GNU Guix's official channel records, introduction and future defaults
;; sourced from Guix itself. Do not duplicate the upstream fingerprint here.
;;
;; WSM is not authenticated yet. The normal consumer command must refuse its
;; unsigned introduction until the owner completes Phase B. The diagnostic
;; --disable-authentication path is never a release or production path.
;;
(use-modules (guix channels))

(cons*
 (channel
  (name 'wsm)
  (url "https://github.com/juv4uk/wsm-desktop.git")
  (branch "main"))
 %default-channels)
