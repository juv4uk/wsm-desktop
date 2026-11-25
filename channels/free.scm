;; SPDX-License-Identifier: GPL-3.0-or-later
;;
;; WSM Free channel set.
;; This expression retains the official default Guix channels only.
;; Capture an exact snapshot with:
;;   guix describe -f channels > channels.lock.scm

(use-modules (guix channels))

%default-channels
