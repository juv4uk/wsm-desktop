;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Мінімальний приклад Guix System для первинної перевірки у disposable QEMU VM.
;; Це не завершена конфігурація WSM Desktop і не конфігурація інсталятора.
;;
;; У GNU/Linux звичайний \`guix system vm' використовує пряме завантаження ядра
;; і не перевіряє оголошений bootloader. Для повного BIOS/GRUB-шляху застосовуйте
;; \`guix system vm --full-boot' у відокремленій BIOS/SeaBIOS VM.
;; \`guix system image --image-type=qcow2' — окрема операція генерації образу.
;; Для UEFI потрібні grub-efi-bootloader, ESP у /boot/efi та GPT.
;; Деталі й зафіксовані межі перевірки див. у systems/README.md.

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
