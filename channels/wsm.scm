;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM channel set: the official Guix channel plus this repository as a channel.
;;
;; This is a development channel set, not a release lock. The official Guix
;; channel is inherited from %default-channels so Guix supplies its built-in
;; introduction and default branch. WSM follows main but has no introduction
;; yet; ordinary authenticated use must therefore fail closed until the owner
;; completes the signed-introduction/.guix-authorizations/keyring bootstrap.
;;
;; Diagnostic only (never use in a release or installer workflow):
;;
;;   guix time-machine -C channels/wsm.scm -- describe -f channels
;;   guix time-machine -C channels/wsm.scm --disable-authentication -- describe -f channels
;;
;; The second command deliberately disables the authentication check and is
;; not evidence that the WSM channel is authenticated.
;;
;; Keep this expression aligned with channels/free.scm and compatibility.scm:
;; one explicit WSM channel added to %default-channels.

(use-modules (guix channels))

(cons*
 (channel
  (name 'wsm)
  (url "https://github.com/juv4uk/wsm-desktop")
  (branch "main"))
 %default-channels)
