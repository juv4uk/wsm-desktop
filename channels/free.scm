;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; WSM Free channel set.
;; This expression retains the official default Guix channels only.
;; Capture an exact snapshot with:
;;   guix describe -f channels > channels.lock.scm

(use-modules (guix channels))

%default-channels
