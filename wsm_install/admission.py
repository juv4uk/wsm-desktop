# SPDX-License-Identifier: LicenseRef-Volnist
"""One report that says what APPLY would require, and where it would stop.

The installer now has four separate contracts: a plan digest, per-step consent, a
disk identity re-check, and a postcondition per allowlisted step. Each is tested on
its own; nothing yet puts them in the order a real apply would use them. This module
is that order, expressed as a value instead of a comment:

    identity  ->  admissibility  ->  consent  ->  postcondition

The order is not arbitrary. Identity comes first because a drifted target makes
every later answer meaningless. Admissibility comes before consent because asking a
person to approve `/bin/sh -c …` would be a prompt that can never be honoured.
Consent comes before the postcondition because a postcondition describes what to
check after a write, and there is no write without consent.

It reports, it does not apply. `wsm_install.executor.execute` stays preview-only and
`dry_run=False` still refuses, so this report is the admission ticket an apply path
will one day need — not the apply path itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from wsm_install.consent import ConsentError, needs_consent, require_consent
from wsm_install.disk_identity import (
    DiskIdentity,
    DiskObserver,
    IdentityError,
    require_unchanged,
)
from wsm_install.executor import admissible_executable
from wsm_install.install_steps import Step
from wsm_install.plan_digest import PlanDigestError, plan_digest, step_digest
from wsm_install.verify import Observer, verify_step


@dataclass(frozen=True)
class StepAdmission:
    index: int
    step_digest: str
    destructive: bool
    status: str  # "admitted" or "refused"
    reason: str = ""


@dataclass(frozen=True)
class AdmissionReport:
    plan_digest: str
    status: str  # "admitted" or "refused"
    reason: str
    steps: tuple[StepAdmission, ...]

    def refused_steps(self) -> tuple[StepAdmission, ...]:
        return tuple(step for step in self.steps if step.status != "admitted")


ConsentFor = Callable[[int, Step, str], bool]


def admit(
    steps: Sequence[Step],
    disk: str,
    *,
    expected_identity: DiskIdentity,
    disk_observer: DiskObserver,
    observer: Observer,
    consent_for: ConsentFor | None = None,
) -> AdmissionReport:
    """Run the admission chain and report per-step verdicts. Never writes.

    `expected_identity` is what the target looked like when the plan was built —
    captured then, not now. Re-capturing here would compare the device with itself
    and detect nothing, which is the mistake the prototype made with its single
    string comparison.
    """
    try:
        require_unchanged(expected_identity, disk_observer)
        plan = plan_digest(disk, steps)
    except (IdentityError, PlanDigestError) as exc:
        return AdmissionReport(
            plan_digest="",
            status="refused",
            reason=f"{exc.code}: {exc.message}",
            steps=(),
        )

    verdicts: list[StepAdmission] = []
    for index, step in enumerate(steps, start=1):
        single = step_digest(disk, step, index)
        destructive = needs_consent(step)

        admissible, why = admissible_executable(step)
        if not admissible:
            verdicts.append(
                StepAdmission(index, single, destructive, "refused", f"inadmissible: {why}")
            )
            continue

        if destructive:
            granted = consent_for(index, step, single) if consent_for is not None else False
            try:
                require_consent(
                    None if not granted else _grant(disk, steps, index),
                    disk,
                    steps,
                    index,
                )
            except ConsentError as exc:
                verdicts.append(
                    StepAdmission(index, single, destructive, "refused", f"{exc.code}: {exc.message}")
                )
                continue

        verification = verify_step(step, observer)
        if verification.status != "verified":
            verdicts.append(
                StepAdmission(
                    index, single, destructive, "refused", f"{verification.status}: {verification.detail}"
                )
            )
            continue

        verdicts.append(StepAdmission(index, single, destructive, "admitted"))

    refused = [verdict for verdict in verdicts if verdict.status != "admitted"]
    if refused:
        return AdmissionReport(
            plan_digest=plan,
            status="refused",
            reason=f"{len(refused)} of {len(verdicts)} steps are not admissible",
            steps=tuple(verdicts),
        )
    return AdmissionReport(plan_digest=plan, status="admitted", reason="", steps=tuple(verdicts))


def _grant(disk: str, steps: Sequence[Step], index: int):
    from wsm_install.consent import grant_consent

    return grant_consent(disk, steps, index, approve=True)
