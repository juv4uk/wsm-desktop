;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Перший H170 Free package-set: лише два upstream roots для окремої перевірки.
;; Джерело: офіційний GNU Guix channel з channels.lock.scm
;; (commit 4e5195be20d9b124df8a8bb69213412236e4668e).
;;
;; Це manifest для ephemeral evaluation/build evidence, а не дозвіл на export.
;; Не додавати сюди WSM-owned packages (#367), Nonguix, linux-firmware,
;; Intel microcode або NVIDIA firmware (#586). H170 hardware facts лишаються
;; у drivers/profiles/h170-free.json.
;;
;; linux-libre 7.3.5 залишається лише кандидатом: відомий GP107 Nouveau
;; atomic-init fix відсутній у цьому pin (#514). Успішна збірка не означає,
;; що GTX 1050 Ti працює на H170.

(use-modules (guix profiles))

(specifications->manifest
 '("linux-libre"
   "mesa"))
