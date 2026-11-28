;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; H170 Free candidate package set for pinned upstream Guix.
;; This is a build/evidence manifest, not a supported-hardware verdict or a release lock.
;; Evaluate only with channels.lock.scm (the official Guix channel).
;;
;; Deliberately excluded:
;; - wsm-tools: unresolved effective-license mismatch in #367.
;; - linux-firmware, Intel microcode and NVIDIA firmware: firmware/license gates #519/#586.
;; - Nonguix and proprietary NVIDIA drivers: Compatibility-only, not Free.
;;
;; Known limitation: locked linux-libre is 7.3.5. The GP107 Nouveau atomic-init
;; fix ed7fb901fce31588bd12ab95adc36ebcb51bc8ea is absent from this pinned source.
;; Building this package does not prove H170/GP107 boot, binding, 3D or compute.
;;
;; Packages: kernel; open Mesa/Vulkan userspace; read-only hardware/service tools.
(specifications->manifest
 '(
   "linux-libre"
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
