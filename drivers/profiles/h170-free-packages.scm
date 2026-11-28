;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; H170 Free package roots from the pinned official Guix channel.
;; This manifest contains only upstream Guix packages; it intentionally excludes
;; WSM-owned tools, Nonguix, proprietary NVIDIA drivers and nonfree firmware.
;; The WSM-owned linux-libre-h170 kernel overlay is built and released separately.
(specifications->manifest
 '("mesa"
   "vulkan-loader"
   "vulkan-tools"
   "pciutils"
   "usbutils"
   "alsa-utils"
   "ethtool"
   "nvme-cli"
   "smartmontools"
   "lm-sensors"))
