# SPDX-License-Identifier: LicenseRef-Volnist
"""Per-step consent, bound to the exact plan and the exact command it authorises.

#280 acceptance criterion 4: every destructive operation needs its own explicit
consent, bound to the disk fingerprint and the command digest, and a cancelled or
rejected consent must not reach the runner.

The prototype behind the issue checked `acknowledgement == disk` once, before the
loop, while the documentation promised re-consent before each destructive step.
A single string comparison cannot express "this command, at this position, in this
plan, against this disk" — so the grant is a record, not a boolean, and it is
validated against the plan digest and the step digest computed in
`wsm_install.plan_digest`.

Nothing here prompts a human. `grant_consent` takes the decision as an argument,
so the caller owns the interface (a TUI, a CLI flag, a test) and this module stays
pure and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from wsm_install.install_steps import Step
from wsm_install.plan_digest import PlanDigestError, plan_digest, step_digest


class ConsentError(Exception):
    """A refusal with a stable code, like the rest of the installer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ConsentGrant:
    """What a person approved: one step, in one plan, against one disk."""

    plan_digest: str
    step_index: int
    step_digest: str


def needs_consent(step: Step) -> bool:
    """Only destructive steps need a fresh grant."""
    return bool(step.destructive)


def grant_consent(
    disk: str,
    steps: Sequence[Step],
    index: int,
    *,
    approve: bool,
) -> ConsentGrant | None:
    """Record a decision for one step. A refusal is None, never a false grant."""
    try:
        plan = plan_digest(disk, steps)
        step = _step_at(steps, index)
        single = step_digest(disk, step, index)
    except PlanDigestError as exc:
        raise ConsentError(exc.code, exc.message) from exc

    if not approve:
        return None
    return ConsentGrant(plan_digest=plan, step_index=index, step_digest=single)


def require_consent(
    grant: ConsentGrant | None,
    disk: str,
    steps: Sequence[Step],
    index: int,
) -> None:
    """Raise unless this step is authorised by a grant matching the current plan.

    Order of checks matters for the message the operator sees: a missing grant is
    "nobody was asked", a stale plan is "the plan changed after you agreed", and a
    digest mismatch is "you agreed to a different command".
    """
    step = _step_at(steps, index)
    if not needs_consent(step):
        return
    if grant is None:
        raise ConsentError(
            "consent.missing",
            f"step {index} is destructive and was not approved",
        )

    try:
        current_plan = plan_digest(disk, steps)
        current_step = step_digest(disk, step, index)
    except PlanDigestError as exc:
        raise ConsentError(exc.code, exc.message) from exc

    if grant.plan_digest != current_plan:
        raise ConsentError(
            "consent.stale-plan",
            f"step {index}: the plan changed after consent was given",
        )
    if grant.step_index != index or grant.step_digest != current_step:
        raise ConsentError(
            "consent.mismatch",
            f"step {index}: consent was given for a different command or position",
        )


def _step_at(steps: Sequence[Step], index: int) -> Step:
    if not isinstance(index, int) or index < 1:
        raise ConsentError("consent.index", "step index must be a positive integer")
    if index > len(steps):
        raise ConsentError(
            "consent.index",
            f"step index {index} is outside the plan of {len(steps)} steps",
        )
    return steps[index - 1]
