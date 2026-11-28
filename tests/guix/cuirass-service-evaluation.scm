;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; This is a configuration/API evaluation only. It does not start Cuirass,
;; register a jobset, connect to PostgreSQL, or build packages.

(use-modules (gnu services)
             (gnu services cuirass)
             (ci cuirass images))

(load "ci/cuirass/service.scm")

(unless (eq? (service-kind wsm-cuirass-service) cuirass-service-type)
  (error "WSM Cuirass fragment did not create a cuirass-service-type service"))

(unless (procedure? cuirass-jobs)
  (error "Cuirass custom job module does not export cuirass-jobs"))

(display "WSM Cuirass service record and custom job module evaluated successfully; no service was started.\n")
