;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; H170 Free upstream package roots — candidate set, not a hardware profile.
;;
;; Evaluate with the official Guix channel lock:
;;   guix time-machine -C channels.lock.scm -- build \
;;     --system=x86_64-linux --manifest=manifests/h170-free-upstream.scm \
;;     --dry-run
;;
;; This manifest contains only packages defined by the official Guix channel.
;; It contains no WSM-owned package, Nonguix package, proprietary driver,
;; firmware blob, microcode, or hardware-test command.
;;
;; A manifest/package evaluation is not an H170 native-Linux test, an image
;; build, a runtime driver test, or permission to redistribute store outputs.
;; Do not export NARs or publish substitutes while #367 / channel trust /
;; endpoint and signing-key custody decisions remain open.

(use-modules (gnu packages disk)
             (gnu packages gl)
             (gnu packages linux)
             (gnu packages video)
             (guix profiles))

(packages->manifest
 (list
  ;; Kernel and graphics stack from the pinned, official Guix snapshot.
  ;; Mesa's x86_64-linux recipe enables the Nouveau Vulkan driver at build time;
  ;; that does not supply GP107 FECS/GPCCS firmware or prove runtime acceleration.
  linux-libre
  mesa
  ;; Candidate video path for the Skylake i915 generation.  Firmware-backed
  ;; power-management/media capabilities remain separate and unassessed.
  intel-vaapi-driver

  ;; The exact live-installer tool families required by the H170 Free plan.
  gptfdisk
  parted
  dosfstools
  e2fsprogs

  ;; Read-only inventory and audio utilities; their presence does not prove
  ;; that the corresponding physical controller binds or works.
  usbutils
  alsa-utils))
