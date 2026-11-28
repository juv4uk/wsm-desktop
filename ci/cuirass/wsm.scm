;; SPDX-License-Identifier: LicenseRef-Volnist
;; Cuirass job specification for WSM Desktop.
;;
;; Register it with:
;;
;;   guix time-machine -C channels.lock.scm -- \
;;        cuirass register --specifications ci/cuirass/wsm.scm
;;
;; or, against a running instance, point its specification directory here. The
;; channels are read from the same locked file the image build uses, so a Cuirass
;; build and a release build resolve identical inputs. A spec that pins its own
;; channel list would drift from the lock the moment either changes, which is the
;; failure this repository already spent effort removing elsewhere.
;;
;; What it builds, in dependency order:
;;   wsm-tools    — the installer and CLI as one package;
;;   wsm-live     — the full live image definition;
;;   wsm-live-minimal — the image the release workflow actually ships.
;;
;; Cuirass is a build service, not an acceptance gate: a green build means the
;; derivation built, not that the image boots or that the installer's tools are in
;; it. Those stay in the QEMU harness and the release workflow, where a boot can
;; be observed. Do not read a Cuirass green as a release approval.

(list
 (specification
  (name "wsm-desktop")
  (build '(
           ;; The installer package. Builds the same derivation the release
           ;; workflow's `guix build` does, from the locked channels.
           (job "wsm-tools"
                #:derivation
                `(begin
                   (use-modules (wsm packages wsm))
                   wsm-tools))

           ;; The minimal live image: the one the release publishes. Named here
           ;; because it is the artefact whose absence would be discovered last.
           (job "wsm-live-minimal"
                #:derivation
                `(begin
                   (use-modules (gnu)
                                (wsm packages wsm))
                   (operating-system-derivation
                    (load "systems/live-minimal.scm"))))))
  (priority 1)))
