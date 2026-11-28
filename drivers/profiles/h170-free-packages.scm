;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; H170 Free package roots from the pinned official Guix channel.
;; This manifest contains only upstream Guix package roots; WSM-owned tools and
;; nonfree driver/firmware payloads are deliberately outside this package set.
;; The WSM-owned linux-libre-h170 kernel overlay is built and released separately.
(specifications->manifest
 '(
   "mesa"
   "vulkan-loader"
   "vulkan-tools"
   "pciutils"
   "usbutils"
   "alsa-utils"
   "ethtool"
   "nvme-cli"
   "smartmontools"
   "lm-sensors"))
