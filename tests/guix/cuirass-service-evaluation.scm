;; SPDX-License-Identifier: LicenseRef-Volnist
;;
;; Configuration/API evaluation only. This does not start Cuirass, register a
;; jobset, connect to PostgreSQL, publish substitutes, or build packages.

(use-modules (gnu services)
             (gnu services cuirass)
             (ci cuirass images))

(load "ci/cuirass/service.scm")

(unless (eq? (service-kind wsm-cuirass-service) cuirass-service-type)
  (error "WSM Cuirass fragment did not create the expected service type"))

(unless (procedure? cuirass-jobs)
  (error "Cuirass custom job module does not export a callable cuirass-jobs"))

(display "Cuirass service and custom job module evaluated; no service was started.\n")
