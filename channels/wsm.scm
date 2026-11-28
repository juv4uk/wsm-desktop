;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Development channel set: WSM plus GNU Guix's canonical default channels.
;;
;; Reuse %default-channels instead of copying the official Guix channel record:
;; its branch and introduction metadata remain owned by the Guix revision in
;; use. WSM intentionally remains unauthenticated until the owner completes
;; Phase B (signed introduction, .guix-authorizations and public keyring).
;;
;; The ordinary Guix invocation must therefore reject WSM for its missing
;; introduction. --disable-authentication is diagnostic-only and never belongs
;; in release, installer or production commands.

(use-modules (guix channels))

(cons*
 (channel
  (name 'wsm)
  (url "https://github.com/juv4uk/wsm-desktop.git")
  (branch "main"))
 %default-channels)
