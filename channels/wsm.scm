;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Development channel set: WSM plus the canonical official Guix defaults.
;;
;; The WSM channel is intentionally unauthenticated until the owner completes
;; Phase B: signed introduction, .guix-authorizations and the public keyring.
;; Ordinary Guix authentication must therefore reject this channel for the
;; specific WSM trust reason. Never use --disable-authentication in production.
;;
;; Reusing %default-channels avoids copying Guix's official introduction and
;; branch metadata into a second record that can drift from Guix itself.

(use-modules (guix channels))

(cons*
 (channel
  (name 'wsm)
  (url "https://github.com/juv4uk/wsm-desktop.git")
  (branch "main"))
 %default-channels)
