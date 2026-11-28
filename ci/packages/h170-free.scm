;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; H170 Free hardware package set — build/evaluation manifest only.
;;
;; It uses only package definitions from the official Guix channel pinned by
;; channels.lock.scm.  It deliberately excludes all WSM-owned packages,
;; Nonguix, linux-firmware/NVIDIA firmware, and proprietary NVIDIA drivers.
;;
;; This manifest is NOT an export list and does not authorize NAR publication.
;; See ci/packages/README.md and issues #367, #586, #39, #534.

(use-modules (guix profiles)
             (gnu packages linux)
             (gnu packages gl)
             (gnu packages vulkan)
             (gnu packages video)
             (gnu packages admin)
             (gnu packages disk)
             (gnu packages pciutils)
             (gnu packages networking))

(packages->manifest
 (list
  ;; Kernel / core stack.  The pinned linux-libre 7.3.5 candidate has the
  ;; separately documented GP107 Nouveau atomic-KMS regression risk.
  linux-libre
  mesa
  mesa-utils
  vulkan-loader
  vulkan-tools

  ;; Intel HD Graphics 530 (Skylake / Gen9) media candidates.  Package
  ;; availability/build does not prove codec or hardware acceleration.
  intel-media-driver
  intel-vaapi-driver
  libva-utils

  ;; GPU and platform diagnostics; these do not change driver state.
  igt-gpu-tools
  pciutils
  usbutils
  dmidecode
  lshw

  ;; Owner-inventoried storage and audio diagnostics / installer tools.
  nvme-cli
  smartmontools
  alsa-utils
  util-linux
  e2fsprogs
  parted
  gptfdisk
  dosfstools

  ;; Owner-inventoried wired networking; Wi-Fi hardware is not identified.
  iproute
  iw
  ethtool))
