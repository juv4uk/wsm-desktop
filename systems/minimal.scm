;; SPDX-License-Identifier: GPL-3.0-or-later
;;
;; Minimal Guix System bring-up example for a disposable VM.
;; This is not the finished WSM Desktop configuration and is not an
;; installer-generated configuration.
;;
;; For a real target, replace the filesystem labels with verified target
;; identifiers and review the bootloader target before any deployment.

(use-modules (gnu))

(operating-system
  (host-name "wsm-desktop")
  (timezone "Europe/Kyiv")
  (locale "en_US.utf8")
  (keyboard-layout (keyboard-layout "us"))

  (bootloader
   (bootloader-configuration
    (bootloader grub-efi-bootloader)
    (targets '("/boot/efi"))))

  (file-systems
   (cons*
    (file-system
      (mount-point "/")
      (device (file-system-label "wsm-root"))
      (type "ext4"))
    (file-system
      (mount-point "/boot/efi")
      (device (file-system-label "wsm-efi"))
      (type "vfat"))
    %base-file-systems)))
