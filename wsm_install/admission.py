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

import re
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

    verdicts = _cover_stateless_steps(steps, disk, verdicts)
    refused = [verdict for verdict in verdicts if verdict.status == "refused"]
    if refused:
        return AdmissionReport(
            plan_digest=plan,
            status="refused",
            reason=f"{len(refused)} of {len(verdicts)} steps are not admissible",
            steps=tuple(verdicts),
        )
    return AdmissionReport(plan_digest=plan, status="admitted", reason="", steps=tuple(verdicts))


_DEVICE = re.compile(r"/dev/[A-Za-z0-9._/-]+")


def _covers(candidate: Step, disk: str) -> bool:
    """Does this step read the device a stateless earlier step was preparing?"""
    for argument in candidate.command:
        for referenced in _DEVICE.findall(argument):
            if referenced == disk or referenced.startswith(disk + "p") or (
                referenced.startswith(disk) and referenced[len(disk):].isdigit()
            ):
                return True
    return False


def _cover_stateless_steps(
    steps: Sequence[Step], disk: str, verdicts: list[StepAdmission]
) -> list[StepAdmission]:
    """Let a later, verified step vouch for an earlier step that has no state of its own.

    `partprobe` and `udevadm settle` deliberately have no postcondition: they ask the
    kernel to notice a new table and wait for device nodes, and leave nothing to read.
    Refusing the whole plan for that would be wrong, and admitting them on their own
    would be the fake success #280 exists to remove.

    The plan itself carries the evidence: if a later step is admitted and reads a
    device under this disk, then the table and the nodes it needed were there. That
    is a plan-level argument, and it is recorded as such — the step stays marked as
    covered rather than verified.
    """
    for position, verdict in enumerate(verdicts):
        if verdict.status != "refused" or "unverified" not in verdict.reason:
            continue
        for later_position in range(position + 1, len(verdicts)):
            later = verdicts[later_position]
            if later.status == "admitted" and _covers(steps[later_position], disk):
                verdicts[position] = StepAdmission(
                    verdict.index,
                    verdict.step_digest,
                    verdict.destructive,
                    "admitted-covered",
                    f"no postcondition of its own; covered by step {later.index}",
                )
                break
    return verdicts


def _grant(disk: str, steps: Sequence[Step], index: int):
    from wsm_install.consent import grant_consent

    return grant_consent(disk, steps, index, approve=True)
