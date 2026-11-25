;; SPDX-License-Identifier: GPL-3.0-or-later
;;
;; Minimal Guix System bring-up example for a disposable QEMU VM.
;; This is not the finished WSM Desktop configuration and is not an
;; installer-generated configuration.
;;
;; On GNU/Linux, \`guix system vm' defaults to direct-kernel boot and does
;; not exercise the declared bootloader.  Use \`guix system vm --full-boot'
;; to test the complete boot sequence through BIOS GRUB on /dev/vda.
;; \`guix system image --image-type=qcow2' is a separate image-generation
;; action; consult the selected Guix revision's manual for its semantics.
;; For a UEFI target, use grub-efi-bootloader with an EFI System Partition
;; at /boot/efi and verify the target identifiers before deployment.
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
