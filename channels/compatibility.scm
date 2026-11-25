;; SPDX-License-Identifier: GPL-3.0-or-later
;;
;; Optional WSM Compatibility channel set.
;; Nonguix is an independent community channel, not an official Guix channel.
;; This file adds the channel; it does not automatically select a nonfree
;; kernel, firmware, driver, substitute server, or package.
;;
;; Channel introduction values below are taken from Nonguix's published
;; installation instructions. Re-check them against upstream before use.

(use-modules (guix channels))

(cons*
 (channel
  (name 'nonguix)
  (url "https://gitlab.com/nonguix/nonguix")
  (introduction
   (make-channel-introduction
    "897c1a470da759236cc11798f4e0a5f7d4d59fbc"
    (openpgp-fingerprint
     "2A39 3FFF 68F4 EF7A 3D29  12AF 6F51 20A0 22FB B2D5"))))
 %default-channels)
