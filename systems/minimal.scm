;; SPDX-License-Identifier: GPL-3.0-or-later
;;
;; Minimal Guix System bring-up example for a disposable QEMU VM.
;; This is not the finished WSM Desktop configuration and is not an
;; installer-generated configuration.
;;
;; `guix system vm' builds an MBR disk image, so this VM-facing example uses
;; BIOS Grub on /dev/vda.  For a UEFI target, replace the bootloader with
;; `grub-efi-bootloader', mount an EFI System Partition at /boot/efi and
;; verify the target identifiers and bootloader target before deployment.
;; See systems/README.md.

(use-modules (gnu))

(operating-system
  (host-name "wsm-desktop")
  (timezone "Europe/Kyiv")
  (locale "en_US.utf8")
  (keyboard-layout (keyboard-layout "us"))

  (bootloader
   (bootloader-configuration
    (bootloader grub-bootloader)
    (targets '("/dev/vda"))))

  (file-systems
   (cons*
    (file-system
      (mount-point "/")
      (device (file-system-label "wsm-root"))
      (type "ext4"))
    %base-file-systems)))
