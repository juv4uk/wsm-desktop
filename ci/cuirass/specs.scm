;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Cuirass is GNU Guix's native build coordinator. This file is an inert
;; prototype: do not register it until WSM's owner-signed channel trust
;; bootstrap (issue #534 / Phase B) and the licensing decision in issue #367
;; are complete. The live-minimal profile includes wsm-tools, so both jobs
;; below exercise that package metadata and its resulting artifacts.
;;
;; Cuirass builds derivations through guix-daemon. It does not itself publish
;; substitutes; guix publish is a separate service and is not configured here.
;; A green job never replaces BIOS/UEFI or installer acceptance in QEMU.
;;
;; Do not use --disable-authentication, invent a WSM fingerprint, or register
;; these specifications against an unauthenticated WSM channel.
;;
;; The file is a plain list of specifications for a later authenticated
;; registration. See docs/CUIRASS.md for the trust, licensing and deployment
;; gates.
(list
 ;; The channel's own tool package: the smallest job that fails if the pinned
 ;; channels stop being able to build what we ship.
 (specification
  (name "wsm-tools")
  (priority 1)
  (build '(packages "wsm-tools"))
  (channels
   (list (channel
          (name 'guix)
          (url "https://git.guix.gnu.org/guix.git")
          (branch #f)
          (commit "4e5195be20d9b124df8a8bb69213412236e4668e")
          (introduction
           (make-channel-introduction
            "9edb3f66fd807b096b48283debdcddccfea34bad"
            (openpgp-fingerprint
             "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA"))))
         (channel
          (name 'wsm)
          (url "https://github.com/juv4uk/wsm-desktop")
          (branch "main")))))

 ;; The live image derivation. Cuirass builds the same expression the release
 ;; workflow builds, so a broken profile shows up here within one poll interval
 ;; instead of after a forty-minute Actions run.
 (specification
  (name "wsm-live-minimal-image")
  (priority 1)
  (build '(custom (ci cuirass images)))
  (channels
   (list (channel
          (name 'guix)
          (url "https://git.guix.gnu.org/guix.git")
          (branch #f)
          (commit "4e5195be20d9b124df8a8bb69213412236e4668e")
          (introduction
           (make-channel-introduction
            "9edb3f66fd807b096b48283debdcddccfea34bad"
            (openpgp-fingerprint
             "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA"))))
         (channel
          (name 'wsm)
          (url "https://github.com/juv4uk/wsm-desktop")
          (branch "main"))))))
